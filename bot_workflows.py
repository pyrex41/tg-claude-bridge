"""
Enhanced Bot Workflows
Implements plan-and-execute, verification, and reflection patterns
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from task_master_client import TaskMasterClient, Task
from opencode_agent import OpenCodeAgent

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Subtask:
    """Represents a subtask within a task."""
    id: str
    title: str
    description: str
    status: str = "pending"
    parent_id: Optional[str] = None
    acceptance_criteria: List[str] = field(default_factory=list)
    complexity: str = "medium"  # low, medium, high


@dataclass
class ExecutionPlan:
    """Represents a detailed execution plan for a task."""
    task_id: str
    steps: List[Dict[str, Any]]
    estimated_duration: Optional[str] = None
    risks: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_text(self) -> str:
        """Convert plan to human-readable text."""
        text = f"# Execution Plan for Task {self.task_id}\n\n"
        text += f"**Created:** {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        if self.estimated_duration:
            text += f"**Estimated Duration:** {self.estimated_duration}\n"
        text += f"\n## Steps:\n"
        for i, step in enumerate(self.steps, 1):
            text += f"{i}. {step.get('description', 'N/A')}\n"
            if step.get('rationale'):
                text += f"   *Rationale:* {step['rationale']}\n"
        if self.risks:
            text += f"\n## Risks:\n"
            for risk in self.risks:
                text += f"- {risk}\n"
        return text


@dataclass
class Check:
    """Represents a verification check."""
    name: str
    passed: bool
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class Verification:
    """Result of task verification."""
    passed: bool
    checks: List[Check]
    summary: str


@dataclass
class Reflection:
    """Result of task reflection."""
    successes: List[str]
    failures: List[str]
    lessons_learned: List[str]
    suggestions: List[str]

    def to_text(self) -> str:
        """Convert reflection to human-readable text."""
        text = "# Task Reflection\n\n"

        if self.successes:
            text += "## What Worked Well:\n"
            for item in self.successes:
                text += f"- {item}\n"
            text += "\n"

        if self.failures:
            text += "## Challenges/Issues:\n"
            for item in self.failures:
                text += f"- {item}\n"
            text += "\n"

        if self.lessons_learned:
            text += "## Lessons Learned:\n"
            for item in self.lessons_learned:
                text += f"- {item}\n"
            text += "\n"

        if self.suggestions:
            text += "## Suggestions for Future:\n"
            for item in self.suggestions:
                text += f"- {item}\n"

        return text


# ============================================================================
# Task Decomposition
# ============================================================================

class TaskDecomposer:
    """Handles intelligent task breakdown using task-master subtasks."""

    def __init__(self, task_client: TaskMasterClient, agent: OpenCodeAgent):
        self.task_client = task_client
        self.agent = agent

    async def get_or_create_subtasks(self, task: Task) -> List[Subtask]:
        """
        Get existing subtasks or create them.

        Priority order:
        1. Read existing subtasks from task-master JSON
        2. Use task-master expand command to generate subtasks
        3. Fallback to LLM-based decomposition
        """
        logger.info(f"Getting subtasks for task {task.id}")

        # Try to read existing subtasks from JSON
        subtasks = await self._read_subtasks_from_json(task.id)
        if subtasks:
            logger.info(f"Found {len(subtasks)} existing subtasks for {task.id}")
            return subtasks

        # Try to expand using task-master CLI
        try:
            logger.info(f"Attempting to expand task {task.id} using task-master")
            await self.task_client._run_command(
                "expand",
                f"--id={task.id}",
                "--research",
                timeout=120  # Expansion can take time
            )
            # Read subtasks after expansion
            subtasks = await self._read_subtasks_from_json(task.id)
            if subtasks:
                logger.info(f"Generated {len(subtasks)} subtasks via task-master expand")
                return subtasks
        except Exception as e:
            logger.warning(f"Task-master expand failed: {e}")

        # Fallback to LLM-based decomposition
        logger.info("Falling back to LLM-based task decomposition")
        return await self._llm_decompose(task)

    async def _read_subtasks_from_json(self, task_id: str) -> List[Subtask]:
        """Read subtasks from task-master JSON file."""
        try:
            import json
            import os

            tasks_file = os.path.join(
                self.task_client.working_dir,
                ".taskmaster",
                "tasks",
                "tasks.json"
            )

            if not os.path.exists(tasks_file):
                return []

            with open(tasks_file, 'r') as f:
                data = json.load(f)

            # Find task in any tag
            for tag_name, tag_data in data.items():
                if isinstance(tag_data, dict) and 'tasks' in tag_data:
                    for task_data in tag_data['tasks']:
                        if str(task_data.get('id')) == str(task_id):
                            # Found the task, check for subtasks
                            subtask_list = task_data.get('subtasks', [])
                            if not subtask_list:
                                return []

                            # Convert to Subtask objects
                            subtasks = []
                            for st_data in subtask_list:
                                subtasks.append(Subtask(
                                    id=str(st_data.get('id', '')),
                                    title=st_data.get('title', ''),
                                    description=st_data.get('description', ''),
                                    status=st_data.get('status', 'pending'),
                                    parent_id=task_id,
                                    acceptance_criteria=st_data.get('acceptanceCriteria', []),
                                    complexity=st_data.get('complexity', 'medium')
                                ))
                            return subtasks

            return []

        except Exception as e:
            logger.error(f"Failed to read subtasks from JSON: {e}")
            return []

    async def _llm_decompose(self, task: Task) -> List[Subtask]:
        """Use LLM to break down task when task-master unavailable."""
        prompt = f"""Break down this task into 3-7 concrete, actionable subtasks:

**Task:** {task.title}

**Description:** {task.description}

For each subtask, provide:
1. **Title**: Clear, action-oriented title (e.g., "Implement authentication middleware")
2. **Description**: What needs to be done specifically
3. **Acceptance Criteria**: 2-3 bullet points of what "done" looks like
4. **Complexity**: low, medium, or high

Format your response as a JSON array like this:
[
  {{
    "title": "Subtask title",
    "description": "What needs to be done",
    "acceptanceCriteria": ["Criterion 1", "Criterion 2"],
    "complexity": "medium"
  }}
]

Only respond with the JSON array, no other text."""

        try:
            response = await self.agent.run(prompt, continue_session=False)

            # Extract JSON from response
            import json
            import re

            # Try to find JSON in the response
            json_match = re.search(r'\[[\s\S]*\]', response.content)
            if not json_match:
                logger.error("No JSON found in LLM response")
                return []

            subtask_data = json.loads(json_match.group())

            # Convert to Subtask objects
            subtasks = []
            for i, st_data in enumerate(subtask_data, 1):
                subtask_id = f"{task.id}.{i}"
                subtasks.append(Subtask(
                    id=subtask_id,
                    title=st_data.get('title', ''),
                    description=st_data.get('description', ''),
                    status='pending',
                    parent_id=task.id,
                    acceptance_criteria=st_data.get('acceptanceCriteria', []),
                    complexity=st_data.get('complexity', 'medium')
                ))

            logger.info(f"LLM generated {len(subtasks)} subtasks")
            return subtasks

        except Exception as e:
            logger.error(f"LLM decomposition failed: {e}")
            # Return a simple default subtask
            return [Subtask(
                id=f"{task.id}.1",
                title=task.title,
                description=task.description,
                status='pending',
                parent_id=task.id
            )]


# ============================================================================
# Progress Logging
# ============================================================================

class TaskMasterLogger:
    """Handles all task-master progress logging."""

    def __init__(self, task_client: TaskMasterClient):
        self.task_client = task_client

    async def log_plan(self, task_id: str, plan: ExecutionPlan):
        """Log execution plan to task-master."""
        try:
            plan_text = plan.to_text()
            await self._update_subtask(
                task_id=task_id,
                prompt=f"📋 EXECUTION PLAN:\n{plan_text}"
            )
            logger.info(f"Logged plan for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to log plan: {e}")

    async def log_progress(self, task_id: str, step_name: str, result: str):
        """Log step progress to task-master."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await self._update_subtask(
                task_id=task_id,
                prompt=f"[{timestamp}] ✓ {step_name}:\n{result}"
            )
            logger.info(f"Logged progress for task {task_id}: {step_name}")
        except Exception as e:
            logger.error(f"Failed to log progress: {e}")

    async def log_subtask_start(self, subtask: Subtask):
        """Log subtask start."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await self._update_subtask(
                task_id=subtask.id,
                prompt=f"[{timestamp}] 🚀 STARTED: {subtask.title}"
            )
        except Exception as e:
            logger.error(f"Failed to log subtask start: {e}")

    async def log_subtask_complete(self, subtask: Subtask, summary: str):
        """Log subtask completion."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await self._update_subtask(
                task_id=subtask.id,
                prompt=f"[{timestamp}] ✅ COMPLETED:\n{summary}"
            )
        except Exception as e:
            logger.error(f"Failed to log subtask completion: {e}")

    async def log_error(self, task_id: str, error: str, recovery: str):
        """Log errors and recovery attempts."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await self._update_subtask(
                task_id=task_id,
                prompt=f"[{timestamp}] ❌ ERROR:\n{error}\n\n🔄 RECOVERY:\n{recovery}"
            )
        except Exception as e:
            logger.error(f"Failed to log error: {e}")

    async def log_reflection(self, task_id: str, reflection: Reflection):
        """Log reflection to task-master."""
        try:
            reflection_text = reflection.to_text()
            await self._update_subtask(
                task_id=task_id,
                prompt=f"💡 {reflection_text}"
            )
            logger.info(f"Logged reflection for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to log reflection: {e}")

    async def _update_subtask(self, task_id: str, prompt: str):
        """Call task-master update-subtask command."""
        try:
            # Use CLI command
            await self.task_client._run_command(
                "update-subtask",
                f"--id={task_id}",
                f"--prompt={prompt}",
                timeout=60
            )
        except Exception as e:
            logger.warning(f"Failed to update subtask via CLI: {e}")
            # Fallback: just log it locally
            logger.info(f"[TaskMaster Log for {task_id}] {prompt[:200]}")


# ============================================================================
# Planner Agent
# ============================================================================

class PlannerAgent:
    """Creates detailed execution plans for tasks."""

    def __init__(self, agent: OpenCodeAgent):
        self.agent = agent

    async def create_plan(
        self,
        task: Task,
        subtasks: List[Subtask],
        extra_context: str = ""
    ) -> ExecutionPlan:
        """
        Create detailed execution plan.

        The plan outlines:
        1. Approach and strategy
        2. Step-by-step breakdown
        3. Potential risks
        4. Estimated duration
        """
        logger.info(f"Creating execution plan for task {task.id}")

        prompt = f"""You are a senior software architect creating an execution plan.

**Task:** {task.title}

**Description:** {task.description}

**Subtasks:**
{self._format_subtasks(subtasks)}

{f"**Additional Context:** {extra_context}" if extra_context else ""}

Create a detailed execution plan with:

1. **Overall Approach**: High-level strategy (2-3 sentences)
2. **Steps**: Break down into specific, ordered steps (one per subtask or group of subtasks)
   - For each step: what to do, why, and what success looks like
3. **Potential Risks**: What could go wrong (2-3 items)
4. **Estimated Duration**: Rough time estimate

Format as JSON:
{{
  "approach": "High-level strategy...",
  "steps": [
    {{
      "description": "What to do",
      "rationale": "Why this step",
      "success_criteria": "What done looks like"
    }}
  ],
  "risks": ["Risk 1", "Risk 2"],
  "estimated_duration": "X hours"
}}

Only respond with the JSON, no other text."""

        try:
            response = await self.agent.run(prompt, continue_session=False)

            # Parse JSON response
            import json
            import re

            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if not json_match:
                raise ValueError("No JSON found in response")

            plan_data = json.loads(json_match.group())

            return ExecutionPlan(
                task_id=task.id,
                steps=plan_data.get('steps', []),
                estimated_duration=plan_data.get('estimated_duration'),
                risks=plan_data.get('risks', [])
            )

        except Exception as e:
            logger.error(f"Plan creation failed: {e}")
            # Return simple fallback plan
            steps = [
                {
                    "description": st.title,
                    "rationale": st.description,
                    "success_criteria": " AND ".join(st.acceptance_criteria) if st.acceptance_criteria else "Subtask complete"
                }
                for st in subtasks
            ]
            return ExecutionPlan(
                task_id=task.id,
                steps=steps if steps else [{"description": task.title, "rationale": task.description}]
            )

    def _format_subtasks(self, subtasks: List[Subtask]) -> str:
        """Format subtasks for display."""
        if not subtasks:
            return "(No subtasks defined)"

        text = ""
        for st in subtasks:
            text += f"- **{st.id}**: {st.title}\n"
            if st.acceptance_criteria:
                text += f"  Acceptance: {', '.join(st.acceptance_criteria)}\n"
        return text


# ============================================================================
# Verification Agent
# ============================================================================

class VerificationAgent:
    """Verifies work against requirements before marking complete."""

    def __init__(self, agent: OpenCodeAgent):
        self.agent = agent

    async def verify_task(
        self,
        task: Task,
        subtasks: List[Subtask],
        plan: ExecutionPlan
    ) -> Verification:
        """
        Verify task completion.

        Checks:
        1. All subtasks marked complete
        2. Implementation matches requirements
        3. No critical errors
        """
        logger.info(f"Verifying task {task.id}")

        checks = []

        # Check 1: All subtasks complete
        subtask_check = self._check_subtasks_complete(subtasks)
        checks.append(subtask_check)

        # Check 2: Implementation verification (LLM-based)
        impl_check = await self._verify_implementation(task, plan)
        checks.append(impl_check)

        # Generate summary
        passed = all(c.passed for c in checks)
        summary = self._generate_summary(checks)

        return Verification(
            passed=passed,
            checks=checks,
            summary=summary
        )

    def _check_subtasks_complete(self, subtasks: List[Subtask]) -> Check:
        """Check if all subtasks are marked complete."""
        if not subtasks:
            return Check(
                name="Subtask Completion",
                passed=True,
                message="No subtasks defined"
            )

        incomplete = [st for st in subtasks if st.status != "done"]

        if incomplete:
            return Check(
                name="Subtask Completion",
                passed=False,
                message=f"{len(incomplete)}/{len(subtasks)} subtasks incomplete: {', '.join(st.id for st in incomplete)}"
            )

        return Check(
            name="Subtask Completion",
            passed=True,
            message=f"All {len(subtasks)} subtasks complete"
        )

    async def _verify_implementation(self, task: Task, plan: ExecutionPlan) -> Check:
        """Use LLM to verify implementation matches requirements."""
        prompt = f"""Verify implementation against requirements.

**Task:** {task.title}
**Requirements:** {task.description}

**Expected Outcome:**
{plan.to_text()}

**Verification:**
1. Check if the code/files exist that implement this task
2. Verify functionality matches requirements
3. Look for any obvious gaps or issues

Respond with EXACTLY this format:
PASSED: yes/no
REASON: brief explanation (one line)
ISSUES: any problems found (or "none")"""

        try:
            response = await self.agent.run(prompt, continue_session=False)
            content = response.content.strip()

            # Parse response
            passed = "PASSED: yes" in content.lower()

            # Extract reason
            reason_match = re.search(r'REASON: (.+)', content, re.IGNORECASE)
            reason = reason_match.group(1).strip() if reason_match else "Unable to parse verification result"

            return Check(
                name="Implementation Verification",
                passed=passed,
                message=reason
            )

        except Exception as e:
            logger.error(f"Implementation verification failed: {e}")
            return Check(
                name="Implementation Verification",
                passed=False,
                message=f"Verification check failed: {str(e)[:100]}"
            )

    def _generate_summary(self, checks: List[Check]) -> str:
        """Generate verification summary."""
        passed_count = sum(1 for c in checks if c.passed)
        total = len(checks)

        summary = f"Verification: {passed_count}/{total} checks passed\n\n"
        for check in checks:
            icon = "✅" if check.passed else "❌"
            summary += f"{icon} **{check.name}**: {check.message}\n"

        return summary


# ============================================================================
# Reflection Agent
# ============================================================================

class ReflectionAgent:
    """Reflects on task execution to learn and improve."""

    def __init__(self, agent: OpenCodeAgent):
        self.agent = agent

    async def reflect_on_task(
        self,
        task: Task,
        plan: ExecutionPlan,
        outcome: str
    ) -> Reflection:
        """
        Reflect on task execution.

        Analyzes:
        1. What went well
        2. What didn't work
        3. Lessons learned
        4. Suggestions for future
        """
        logger.info(f"Reflecting on task {task.id}")

        prompt = f"""Reflect on this completed task to identify learnings.

**Task:** {task.title}
**Description:** {task.description}

**Plan:**
{plan.to_text()}

**Outcome:**
{outcome}

Provide reflection in this JSON format:
{{
  "successes": ["What worked well..."],
  "failures": ["Challenges encountered..."],
  "lessons_learned": ["Key takeaway 1...", "Key takeaway 2..."],
  "suggestions": ["Suggestion for future tasks..."]
}}

Be honest and specific. Focus on learnings that can help with future tasks.
Only respond with JSON, no other text."""

        try:
            response = await self.agent.run(prompt, continue_session=False)

            # Parse JSON
            import json
            import re

            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if not json_match:
                raise ValueError("No JSON in response")

            reflection_data = json.loads(json_match.group())

            return Reflection(
                successes=reflection_data.get('successes', []),
                failures=reflection_data.get('failures', []),
                lessons_learned=reflection_data.get('lessons_learned', []),
                suggestions=reflection_data.get('suggestions', [])
            )

        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            return Reflection(
                successes=[],
                failures=[f"Reflection analysis failed: {str(e)}"],
                lessons_learned=[],
                suggestions=[]
            )
