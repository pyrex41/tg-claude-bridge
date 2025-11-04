"""
Bot Orchestrator
Main workflow orchestration using plan-and-execute pattern
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime

from task_master_client import TaskMasterClient, Task
from opencode_agent import OpenCodeAgent, OpenCodeResponse
from bot_workflows import (
    TaskDecomposer, TaskMasterLogger, PlannerAgent,
    VerificationAgent, ReflectionAgent,
    Subtask, ExecutionPlan
)
from bot_recovery import (
    ErrorRecoveryManager, CheckpointManager, BotTelemetry,
    RecoveryStrategy
)

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class WorkflowConfig:
    """Configuration for workflow behavior."""
    enable_plan_execute: bool = True
    enable_verification: bool = True
    enable_reflection: bool = True
    enable_checkpointing: bool = True
    enable_subtask_decomposition: bool = True
    enable_progress_logging: bool = True
    enable_multi_strategy_retry: bool = True
    max_retry_attempts: int = 4

    @classmethod
    def from_env(cls) -> 'WorkflowConfig':
        """Load configuration from environment variables."""
        def get_bool(key: str, default: bool) -> bool:
            return os.getenv(key, str(default)).lower() == "true"

        return cls(
            enable_plan_execute=get_bool("ENABLE_PLAN_EXECUTE", True),
            enable_verification=get_bool("ENABLE_VERIFICATION", True),
            enable_reflection=get_bool("ENABLE_REFLECTION", True),
            enable_checkpointing=get_bool("ENABLE_CHECKPOINTING", True),
            enable_subtask_decomposition=get_bool("ENABLE_SUBTASK_DECOMPOSITION", True),
            enable_progress_logging=get_bool("ENABLE_PROGRESS_LOGGING", True),
            enable_multi_strategy_retry=get_bool("ENABLE_MULTI_STRATEGY_RETRY", True),
            max_retry_attempts=int(os.getenv("MAX_RETRY_ATTEMPTS", "4"))
        )


# ============================================================================
# Main Orchestrator
# ============================================================================

class PlanExecuteWorkflow:
    """
    Main workflow orchestrator implementing plan-and-execute pattern.

    Workflow phases:
    1. DECOMPOSE: Break task into subtasks
    2. PLAN: Create detailed execution plan
    3. EXECUTE: Work through plan step-by-step
    4. VERIFY: Check work against requirements
    5. REFLECT: Learn from experience
    """

    def __init__(
        self,
        agent: OpenCodeAgent,
        task_client: TaskMasterClient,
        config: Optional[WorkflowConfig] = None
    ):
        self.agent = agent
        self.task_client = task_client
        self.config = config or WorkflowConfig.from_env()

        # Initialize components
        self.decomposer = TaskDecomposer(task_client, agent)
        self.logger = TaskMasterLogger(task_client)
        self.planner = PlannerAgent(agent)
        self.verifier = VerificationAgent(agent)
        self.reflector = ReflectionAgent(agent)
        self.recovery_manager = ErrorRecoveryManager()
        self.checkpoint_manager = CheckpointManager()
        self.telemetry = BotTelemetry()

        logger.info(f"PlanExecuteWorkflow initialized with config: {self.config}")

    async def execute_task(
        self,
        task: Task,
        extra_context: str = "",
        event_callback: Optional[Callable] = None
    ) -> bool:
        """
        Execute task with full workflow.

        Args:
            task: Task to execute
            extra_context: Additional context/instructions
            event_callback: Callback for streaming events to user

        Returns:
            True if task completed successfully, False otherwise
        """
        start_time = datetime.now()
        await self.telemetry.log_task_start(task, {"extra_context": extra_context})

        try:
            logger.info(f"🚀 Starting workflow for task {task.id}: {task.title}")

            # Mark task as in-progress
            await self.task_client.mark_in_progress(task.id)

            # PHASE 1: DECOMPOSE (if enabled)
            subtasks = []
            if self.config.enable_subtask_decomposition:
                subtasks = await self._decompose_phase(task, event_callback)
            else:
                logger.info("Subtask decomposition disabled, treating task as atomic")

            # PHASE 2: PLAN (if enabled)
            plan = None
            if self.config.enable_plan_execute:
                plan = await self._plan_phase(task, subtasks, extra_context, event_callback)
            else:
                logger.info("Planning phase disabled, executing directly")

            # PHASE 3: EXECUTE
            execution_result = await self._execute_phase(
                task, subtasks, plan, extra_context, event_callback
            )

            if not execution_result["success"]:
                duration = (datetime.now() - start_time).total_seconds()
                await self.telemetry.log_task_failed(
                    task,
                    execution_result.get("error", "Unknown error"),
                    {"duration": duration}
                )
                return False

            # PHASE 4: VERIFY (if enabled)
            if self.config.enable_verification:
                verification_passed = await self._verify_phase(
                    task, subtasks, plan, event_callback
                )
                if not verification_passed:
                    logger.warning(f"Task {task.id} verification failed")
                    return False
            else:
                logger.info("Verification phase disabled")

            # PHASE 5: REFLECT (if enabled)
            if self.config.enable_reflection:
                await self._reflect_phase(
                    task, plan, execution_result.get("outcome", ""), event_callback
                )
            else:
                logger.info("Reflection phase disabled")

            # Mark task complete
            await self.task_client.mark_complete(task.id)

            # Clean up checkpoints
            if self.config.enable_checkpointing:
                await self.checkpoint_manager.clear_checkpoints(task.id)

            # Log completion telemetry
            duration = (datetime.now() - start_time).total_seconds()
            await self.telemetry.log_task_complete(
                task,
                duration,
                {
                    "subtasks": len(subtasks),
                    "had_plan": plan is not None,
                    "verified": self.config.enable_verification
                }
            )

            logger.info(f"✅ Task {task.id} completed successfully in {duration:.1f}s")
            return True

        except Exception as e:
            logger.error(f"Workflow error for task {task.id}: {e}", exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            await self.telemetry.log_task_failed(task, str(e), {"duration": duration})
            return False

    async def _decompose_phase(
        self,
        task: Task,
        event_callback: Optional[Callable]
    ) -> list:
        """Phase 1: Decompose task into subtasks."""
        logger.info(f"📋 DECOMPOSE: Breaking down task {task.id}")

        if event_callback:
            await event_callback({
                "type": "phase",
                "message": f"📋 **Phase 1: Task Decomposition**\nAnalyzing task structure..."
            })

        subtasks = await self.decomposer.get_or_create_subtasks(task)

        if event_callback:
            subtask_list = "\n".join(f"  - {st.id}: {st.title}" for st in subtasks)
            await event_callback({
                "type": "phase",
                "message": f"✓ Identified {len(subtasks)} subtasks:\n{subtask_list}"
            })

        return subtasks

    async def _plan_phase(
        self,
        task: Task,
        subtasks: list,
        extra_context: str,
        event_callback: Optional[Callable]
    ) -> Optional[ExecutionPlan]:
        """Phase 2: Create execution plan."""
        logger.info(f"📝 PLAN: Creating execution plan for task {task.id}")

        if event_callback:
            await event_callback({
                "type": "phase",
                "message": f"📝 **Phase 2: Planning**\nCreating detailed execution plan..."
            })

        plan = await self.planner.create_plan(task, subtasks, extra_context)

        # Log plan to task-master
        if self.config.enable_progress_logging:
            await self.logger.log_plan(task.id, plan)

        if event_callback:
            await event_callback({
                "type": "phase",
                "message": f"✓ Plan created with {len(plan.steps)} steps\n\n{plan.to_text()}"
            })

        return plan

    async def _execute_phase(
        self,
        task: Task,
        subtasks: list,
        plan: Optional[ExecutionPlan],
        extra_context: str,
        event_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """Phase 3: Execute the task/plan."""
        logger.info(f"⚙️ EXECUTE: Working on task {task.id}")

        if event_callback:
            await event_callback({
                "type": "phase",
                "message": f"⚙️ **Phase 3: Execution**\nExecuting task..."
            })

        # Build execution prompt
        if plan:
            prompt = self._build_prompt_with_plan(task, plan, extra_context)
        else:
            prompt = self._build_simple_prompt(task, extra_context)

        # Create checkpoint before execution
        if self.config.enable_checkpointing:
            await self.checkpoint_manager.create_checkpoint(
                task_id=task.id,
                state={"phase": "execute", "started": datetime.now().isoformat()},
                subtask_progress={st.id: st.status for st in subtasks}
            )

        # Execute with OpenCode agent
        try:
            response = await self.agent.run(
                prompt=prompt,
                continue_session=True,
                event_callback=event_callback
            )

            # Log progress to task-master
            if self.config.enable_progress_logging:
                await self.logger.log_progress(
                    task.id,
                    "Task execution",
                    response.content[:1000]  # First 1000 chars
                )

            return {
                "success": True,
                "outcome": response.content,
                "response": response
            }

        except Exception as e:
            logger.error(f"Execution error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _verify_phase(
        self,
        task: Task,
        subtasks: list,
        plan: Optional[ExecutionPlan],
        event_callback: Optional[Callable]
    ) -> bool:
        """Phase 4: Verify task completion."""
        logger.info(f"✓ VERIFY: Checking task {task.id}")

        if event_callback:
            await event_callback({
                "type": "phase",
                "message": f"✓ **Phase 4: Verification**\nVerifying implementation..."
            })

        # Skip verification if no plan (can't verify without requirements)
        if not plan:
            logger.info("No plan available, skipping verification")
            return True

        verification = await self.verifier.verify_task(task, subtasks, plan)

        if event_callback:
            await event_callback({
                "type": "phase",
                "message": verification.summary
            })

        return verification.passed

    async def _reflect_phase(
        self,
        task: Task,
        plan: Optional[ExecutionPlan],
        outcome: str,
        event_callback: Optional[Callable]
    ):
        """Phase 5: Reflect on execution."""
        logger.info(f"💡 REFLECT: Reflecting on task {task.id}")

        if event_callback:
            await event_callback({
                "type": "phase",
                "message": f"💡 **Phase 5: Reflection**\nAnalyzing learnings..."
            })

        # Skip reflection if no plan
        if not plan:
            logger.info("No plan available, skipping reflection")
            return

        reflection = await self.reflector.reflect_on_task(task, plan, outcome)

        # Log reflection to task-master
        if self.config.enable_progress_logging:
            await self.logger.log_reflection(task.id, reflection)

        if event_callback:
            await event_callback({
                "type": "phase",
                "message": reflection.to_text()
            })

    def _build_prompt_with_plan(
        self,
        task: Task,
        plan: ExecutionPlan,
        extra_context: str
    ) -> str:
        """Build execution prompt with plan."""
        prompt = f"""I need you to execute this task following the plan below.

**Task:** {task.title}
**Description:** {task.description}

**EXECUTION PLAN:**
{plan.to_text()}

**Instructions:**
1. Follow the plan step-by-step
2. Be thorough and verify your work
3. Use tools as needed
4. Report back with results

**IMPORTANT:** After completing all steps, explicitly state "Task {task.id} is fully implemented and ready" so I know you're done.
"""

        if extra_context:
            prompt += f"\n**Additional Context:**\n{extra_context}\n"

        return prompt

    def _build_simple_prompt(self, task: Task, extra_context: str) -> str:
        """Build simple execution prompt without plan."""
        prompt = f"""I need you to work on this task:

**Task:** {task.title}
**Description:** {task.description}

Please:
1. Analyze what needs to be done
2. Execute the work
3. Verify completion
4. Report back with results

**IMPORTANT:** After completing the task, explicitly state "Task {task.id} is fully implemented and ready" so I know you're done.
"""

        if extra_context:
            prompt += f"\n**Additional Context:**\n{extra_context}\n"

        return prompt

    async def handle_task_with_retry(
        self,
        task: Task,
        extra_context: str = "",
        event_callback: Optional[Callable] = None,
        max_attempts: Optional[int] = None
    ) -> bool:
        """
        Execute task with multi-strategy retry logic.

        Args:
            task: Task to execute
            extra_context: Additional context
            event_callback: Callback for events
            max_attempts: Maximum retry attempts (uses config if None)

        Returns:
            True if task completed, False otherwise
        """
        max_attempts = max_attempts or self.config.max_retry_attempts
        attempt = 1

        while attempt <= max_attempts:
            logger.info(f"Attempt {attempt}/{max_attempts} for task {task.id}")

            if attempt > 1:
                await self.telemetry.log_retry(task, attempt)

            try:
                # Execute task
                success = await self.execute_task(task, extra_context, event_callback)

                if success:
                    return True

                # Task didn't succeed, prepare for retry
                if attempt >= max_attempts:
                    logger.error(f"Task {task.id} failed after {max_attempts} attempts")
                    return False

                # Use recovery manager for retry strategy
                if self.config.enable_multi_strategy_retry:
                    recovery_action = await self.recovery_manager.handle_error(
                        task,
                        Exception("Task execution incomplete"),
                        attempt + 1
                    )

                    logger.info(f"Recovery strategy: {recovery_action.strategy.value}")

                    # Apply recovery strategy
                    if recovery_action.strategy == RecoveryStrategy.ALTERNATIVE_MODEL:
                        # Switch to alternative model
                        old_model = self.agent.model
                        self.agent.model = recovery_action.params.get("model", "xai/grok-code-fast-1")
                        logger.info(f"Switched model: {old_model} -> {self.agent.model}")

                    elif recovery_action.strategy == RecoveryStrategy.DECOMPOSE_FURTHER:
                        # Force re-decomposition
                        logger.info("Forcing task re-decomposition...")
                        # This will happen automatically in next attempt

                    elif recovery_action.strategy == RecoveryStrategy.HUMAN_ESCALATION:
                        logger.warning(f"Task {task.id} needs human intervention")
                        if event_callback:
                            await event_callback({
                                "type": "error",
                                "message": f"⚠️ Task {task.id} needs human intervention after {attempt} attempts"
                            })
                        return False

                    # Update extra_context for next attempt
                    if "extra_context" in recovery_action.params:
                        extra_context = recovery_action.params["extra_context"]

                attempt += 1

            except Exception as e:
                logger.error(f"Error in attempt {attempt}: {e}", exc_info=True)

                if attempt >= max_attempts:
                    return False

                # Record error and get recovery strategy
                if self.config.enable_multi_strategy_retry:
                    recovery_action = await self.recovery_manager.handle_error(
                        task, e, attempt + 1
                    )

                    if recovery_action.strategy == RecoveryStrategy.HUMAN_ESCALATION:
                        return False

                attempt += 1

        return False

    async def get_telemetry_report(self) -> str:
        """Get performance report."""
        return await self.telemetry.generate_report()
