"""
Error Recovery and State Management
Implements multi-strategy retry logic and checkpointing
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from task_master_client import Task

logger = logging.getLogger(__name__)


# ============================================================================
# Error Classification
# ============================================================================

class ErrorType(Enum):
    """Types of errors that can occur."""
    TRANSIENT = "transient"      # Network issues, timeouts
    BLOCKING = "blocking"         # Missing deps, permissions
    CRITICAL = "critical"         # Unexpected failures
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Recovery strategies for different error types."""
    SIMPLE_RETRY = "simple_retry"                # Try same approach again
    ALTERNATIVE_MODEL = "alternative_model"       # Try different AI model
    DECOMPOSE_FURTHER = "decompose_further"       # Break into smaller pieces
    ALTERNATIVE_APPROACH = "alternative_approach" # Use different strategy
    HUMAN_ESCALATION = "human_escalation"        # Ask for help


@dataclass
class RecoveryAction:
    """Represents a recovery action to take."""
    strategy: RecoveryStrategy
    description: str
    params: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Error Recovery Manager
# ============================================================================

class ErrorRecoveryManager:
    """Manages multi-strategy error recovery."""

    # Strategy progression based on attempt number
    STRATEGY_SEQUENCE = [
        RecoveryStrategy.SIMPLE_RETRY,         # Attempt 1: Try again
        RecoveryStrategy.ALTERNATIVE_MODEL,    # Attempt 2: Different model
        RecoveryStrategy.DECOMPOSE_FURTHER,    # Attempt 3: Break down more
        RecoveryStrategy.HUMAN_ESCALATION      # Attempt 4+: Need help
    ]

    def __init__(self):
        self.error_history: Dict[str, List[Dict]] = {}

    async def handle_error(
        self,
        task: Task,
        error: Exception,
        attempt: int,
        context: Optional[Dict[str, Any]] = None
    ) -> RecoveryAction:
        """
        Apply recovery strategy based on error type and attempt number.

        Args:
            task: The task that failed
            error: The exception that occurred
            attempt: Current attempt number (1-indexed)
            context: Additional context about the failure

        Returns:
            RecoveryAction specifying what to do next
        """
        error_type = self._classify_error(error)

        logger.info(
            f"Handling error for task {task.id}: "
            f"type={error_type.value}, attempt={attempt}"
        )

        # Record error in history
        self._record_error(task.id, error, error_type, attempt)

        # Select strategy
        strategy = self._select_strategy(error_type, attempt)

        # Generate action
        action = await self._generate_action(task, error, strategy, attempt, context)

        logger.info(f"Selected recovery strategy: {strategy.value}")
        return action

    def _classify_error(self, error: Exception) -> ErrorType:
        """Classify error as transient, blocking, or critical."""
        error_str = str(error).lower()

        # Transient errors - can be retried
        transient_keywords = [
            "timeout", "network", "connection", "unavailable",
            "503", "502", "504", "temporary"
        ]
        if any(keyword in error_str for keyword in transient_keywords):
            return ErrorType.TRANSIENT

        # Blocking errors - need intervention
        blocking_keywords = [
            "permission", "auth", "not found", "missing",
            "403", "401", "404", "no such file"
        ]
        if any(keyword in error_str for keyword in blocking_keywords):
            return ErrorType.BLOCKING

        # Check exception type
        if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
            return ErrorType.TRANSIENT

        if isinstance(error, (PermissionError, FileNotFoundError)):
            return ErrorType.BLOCKING

        return ErrorType.CRITICAL

    def _select_strategy(self, error_type: ErrorType, attempt: int) -> RecoveryStrategy:
        """Select appropriate recovery strategy."""
        # For blocking errors, escalate immediately
        if error_type == ErrorType.BLOCKING and attempt >= 2:
            return RecoveryStrategy.HUMAN_ESCALATION

        # Otherwise follow standard progression
        if attempt <= len(self.STRATEGY_SEQUENCE):
            return self.STRATEGY_SEQUENCE[attempt - 1]

        # Fallback to escalation for attempts beyond sequence
        return RecoveryStrategy.HUMAN_ESCALATION

    async def _generate_action(
        self,
        task: Task,
        error: Exception,
        strategy: RecoveryStrategy,
        attempt: int,
        context: Optional[Dict[str, Any]]
    ) -> RecoveryAction:
        """Generate specific recovery action based on strategy."""

        if strategy == RecoveryStrategy.SIMPLE_RETRY:
            return RecoveryAction(
                strategy=strategy,
                description=f"Retry task {task.id} with fresh context",
                params={"clear_session": True}
            )

        elif strategy == RecoveryStrategy.ALTERNATIVE_MODEL:
            return RecoveryAction(
                strategy=strategy,
                description=f"Try alternative model for task {task.id}",
                params={
                    "model": "xai/grok-code-fast-1",  # Fast model for retry
                    "extra_context": "Previous attempt failed, try a simpler approach"
                }
            )

        elif strategy == RecoveryStrategy.DECOMPOSE_FURTHER:
            return RecoveryAction(
                strategy=strategy,
                description=f"Break task {task.id} into smaller subtasks",
                params={
                    "force_decompose": True,
                    "max_subtasks": 5
                }
            )

        elif strategy == RecoveryStrategy.ALTERNATIVE_APPROACH:
            return RecoveryAction(
                strategy=strategy,
                description=f"Try different approach for task {task.id}",
                params={
                    "extra_context": self._generate_alternative_context(task, error, context)
                }
            )

        else:  # HUMAN_ESCALATION
            return RecoveryAction(
                strategy=strategy,
                description=f"Task {task.id} needs human intervention after {attempt} attempts",
                params={
                    "error_summary": str(error),
                    "attempts": attempt,
                    "history": self.error_history.get(task.id, [])
                }
            )

    def _generate_alternative_context(
        self,
        task: Task,
        error: Exception,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Generate context for alternative approach."""
        ctx_parts = [
            "Previous approach encountered issues.",
            f"Error: {str(error)[:200]}",
            "",
            "Try a different approach:",
            "- Use simpler implementation",
            "- Focus on core functionality first",
            "- Add error handling",
            "- Check for edge cases"
        ]
        return "\n".join(ctx_parts)

    def _record_error(
        self,
        task_id: str,
        error: Exception,
        error_type: ErrorType,
        attempt: int
    ):
        """Record error in history."""
        if task_id not in self.error_history:
            self.error_history[task_id] = []

        self.error_history[task_id].append({
            "timestamp": datetime.now().isoformat(),
            "attempt": attempt,
            "error_type": error_type.value,
            "error_message": str(error)[:500],
            "exception_type": type(error).__name__
        })

    def get_error_summary(self, task_id: str) -> str:
        """Get formatted error summary for task."""
        if task_id not in self.error_history:
            return "No errors recorded"

        history = self.error_history[task_id]
        summary = f"Error History for {task_id} ({len(history)} attempts):\n\n"

        for entry in history:
            summary += f"**Attempt {entry['attempt']}** ({entry['timestamp']}):\n"
            summary += f"  Type: {entry['error_type']}\n"
            summary += f"  Error: {entry['error_message'][:150]}\n\n"

        return summary


# ============================================================================
# Checkpoint Management
# ============================================================================

@dataclass
class Checkpoint:
    """Represents a saved execution checkpoint."""
    id: str
    task_id: str
    timestamp: datetime
    state: Dict[str, Any]
    subtask_progress: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "state": self.state,
            "subtask_progress": self.subtask_progress,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Checkpoint':
        """Create from dictionary."""
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            state=data.get("state", {}),
            subtask_progress=data.get("subtask_progress", {}),
            metadata=data.get("metadata", {})
        )


class CheckpointManager:
    """Manages execution checkpoints for resumability."""

    def __init__(self, checkpoint_dir: str = "./.bot_checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)
        logger.info(f"Checkpoint directory: {self.checkpoint_dir}")

    async def create_checkpoint(
        self,
        task_id: str,
        state: Dict[str, Any],
        subtask_progress: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Checkpoint:
        """
        Save execution state to checkpoint.

        Args:
            task_id: ID of the task
            state: Current execution state
            subtask_progress: Progress of each subtask (id -> status)
            metadata: Additional metadata

        Returns:
            Created checkpoint
        """
        checkpoint = Checkpoint(
            id=str(uuid.uuid4()),
            task_id=task_id,
            timestamp=datetime.now(),
            state=state,
            subtask_progress=subtask_progress or {},
            metadata=metadata or {}
        )

        # Save to file
        checkpoint_file = self.checkpoint_dir / f"{task_id}_{checkpoint.id}.json"
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

        logger.info(f"Checkpoint created: {checkpoint.id} for task {task_id}")
        return checkpoint

    async def restore_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        """
        Restore most recent checkpoint for task.

        Args:
            task_id: ID of the task

        Returns:
            Most recent checkpoint or None if not found
        """
        checkpoints = list(self.checkpoint_dir.glob(f"{task_id}_*.json"))

        if not checkpoints:
            logger.info(f"No checkpoints found for task {task_id}")
            return None

        # Get most recent by modification time
        latest_file = max(checkpoints, key=lambda p: p.stat().st_mtime)

        with open(latest_file, 'r') as f:
            checkpoint_data = json.load(f)

        checkpoint = Checkpoint.from_dict(checkpoint_data)
        logger.info(f"Restored checkpoint {checkpoint.id} for task {task_id}")
        return checkpoint

    async def list_checkpoints(self, task_id: str) -> List[Checkpoint]:
        """List all checkpoints for a task."""
        checkpoints = []
        for checkpoint_file in self.checkpoint_dir.glob(f"{task_id}_*.json"):
            try:
                with open(checkpoint_file, 'r') as f:
                    checkpoint_data = json.load(f)
                checkpoints.append(Checkpoint.from_dict(checkpoint_data))
            except Exception as e:
                logger.error(f"Failed to load checkpoint {checkpoint_file}: {e}")

        # Sort by timestamp
        checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
        return checkpoints

    async def clear_checkpoints(self, task_id: str):
        """Clear all checkpoints for a completed task."""
        count = 0
        for checkpoint_file in self.checkpoint_dir.glob(f"{task_id}_*.json"):
            try:
                checkpoint_file.unlink()
                count += 1
            except Exception as e:
                logger.error(f"Failed to delete checkpoint {checkpoint_file}: {e}")

        logger.info(f"Cleared {count} checkpoints for task {task_id}")

    async def cleanup_old_checkpoints(self, days: int = 7):
        """Clean up checkpoints older than specified days."""
        import time
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        count = 0

        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                if checkpoint_file.stat().st_mtime < cutoff_time:
                    checkpoint_file.unlink()
                    count += 1
            except Exception as e:
                logger.error(f"Failed to delete old checkpoint {checkpoint_file}: {e}")

        logger.info(f"Cleaned up {count} old checkpoints (older than {days} days)")


# ============================================================================
# Telemetry and Observability
# ============================================================================

from collections import defaultdict


class BotTelemetry:
    """Comprehensive telemetry and observability."""

    def __init__(self):
        self.metrics = {
            "tasks_attempted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_retry_count": 0,
            "avg_task_duration": 0.0,
            "tool_usage": defaultdict(int),
            "error_types": defaultdict(int)
        }
        self.task_logs: List[Dict[str, Any]] = []
        self.session_start = datetime.now()

    async def log_task_start(self, task: Task, metadata: Optional[Dict] = None):
        """Log task start with metadata."""
        log_entry = {
            "task_id": task.id,
            "title": task.title,
            "status": "started",
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.task_logs.append(log_entry)
        self.metrics["tasks_attempted"] += 1
        logger.info(f"📊 Telemetry: Task {task.id} started")

    async def log_task_complete(
        self,
        task: Task,
        duration_seconds: float,
        details: Optional[Dict] = None
    ):
        """Log task completion with metrics."""
        log_entry = {
            "task_id": task.id,
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration_seconds,
            "details": details or {}
        }
        self.task_logs.append(log_entry)
        self.metrics["tasks_completed"] += 1

        # Update average duration
        total_completed = self.metrics["tasks_completed"]
        current_avg = self.metrics["avg_task_duration"]
        self.metrics["avg_task_duration"] = (
            (current_avg * (total_completed - 1) + duration_seconds) / total_completed
        )

        logger.info(
            f"📊 Telemetry: Task {task.id} completed in {duration_seconds:.1f}s"
        )

    async def log_task_failed(self, task: Task, error: str, details: Optional[Dict] = None):
        """Log task failure."""
        log_entry = {
            "task_id": task.id,
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
            "error": error,
            "details": details or {}
        }
        self.task_logs.append(log_entry)
        self.metrics["tasks_failed"] += 1
        logger.info(f"📊 Telemetry: Task {task.id} failed")

    async def log_retry(self, task: Task, attempt: int):
        """Log retry attempt."""
        self.metrics["total_retry_count"] += 1
        logger.info(f"📊 Telemetry: Task {task.id} retry attempt {attempt}")

    async def log_tool_use(self, tool_name: str):
        """Log tool usage."""
        self.metrics["tool_usage"][tool_name] += 1

    async def log_error_type(self, error_type: str):
        """Log error type occurrence."""
        self.metrics["error_types"][error_type] += 1

    async def generate_report(self) -> str:
        """Generate human-readable performance report."""
        total_attempted = self.metrics["tasks_attempted"]
        total_completed = self.metrics["tasks_completed"]
        total_failed = self.metrics["tasks_failed"]

        success_rate = (
            (total_completed / total_attempted * 100)
            if total_attempted > 0
            else 0
        )

        avg_duration = self.metrics["avg_task_duration"]
        session_duration = (datetime.now() - self.session_start).total_seconds()

        report = f"""📊 **Bot Performance Report**

**Session Duration:** {session_duration / 3600:.1f} hours

**Tasks:**
- Attempted: {total_attempted}
- Completed: {total_completed} ✅
- Failed: {total_failed} ❌
- Success Rate: {success_rate:.1f}%

**Performance:**
- Avg Task Duration: {avg_duration:.1f}s
- Total Retries: {self.metrics['total_retry_count']}
- Retry Rate: {self.metrics['total_retry_count'] / max(total_attempted, 1):.2f} per task

"""

        # Tool usage
        if self.metrics["tool_usage"]:
            report += "**Tool Usage:**\n"
            sorted_tools = sorted(
                self.metrics["tool_usage"].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for tool, count in sorted_tools[:10]:
                report += f"  - {tool}: {count}\n"
            report += "\n"

        # Error types
        if self.metrics["error_types"]:
            report += "**Common Errors:**\n"
            sorted_errors = sorted(
                self.metrics["error_types"].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for error, count in sorted_errors[:5]:
                report += f"  - {error}: {count}\n"

        return report

    def get_task_history(self, task_id: Optional[str] = None) -> List[Dict]:
        """Get task history, optionally filtered by task_id."""
        if task_id:
            return [log for log in self.task_logs if log["task_id"] == task_id]
        return self.task_logs
