"""
Task Master CLI Integration
Client for interacting with task-master CLI
"""

import asyncio
import json
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """Represents a task from task-master."""
    id: str
    title: str
    description: str
    status: str
    priority: Optional[str] = None
    dependencies: List[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


class TaskMasterClient:
    """Client for task-master CLI operations."""

    def __init__(self, working_dir: str = "."):
        self.working_dir = working_dir

    async def _run_command(self, *args) -> str:
        """Run a task-master command and return output."""
        cmd = ["task-master"] + list(args)

        logger.info(f"Running: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"task-master error: {error_msg}")
                return f"Error: {error_msg}"

            return stdout.decode().strip()

        except FileNotFoundError:
            logger.error("task-master CLI not found")
            return "Error: task-master CLI not installed"
        except Exception as e:
            logger.error(f"task-master execution error: {e}")
            return f"Error: {e}"

    async def get_next_task(self) -> Optional[Task]:
        """Get the next available task to work on."""
        output = await self._run_command("next")

        if output.startswith("Error:"):
            logger.error(f"Failed to get next task: {output}")
            return None

        # Parse task-master next output
        # Look for "Next Task to Work On: #ID - Title"
        if "no task" in output.lower() or "all tasks complete" in output.lower():
            logger.info("No tasks available")
            return None

        try:
            # Extract from formatted output
            # Pattern: "Next Task to Work On: #10 - Test full session..."
            task_id = None
            title = None

            for line in output.split('\n'):
                line = line.strip()

                # Look for the task ID line
                if "Next Task" in line and "#" in line:
                    # Extract ID and title
                    if "#" in line and "-" in line:
                        parts = line.split("#")[1]  # Get everything after #
                        if "-" in parts:
                            id_part, title_part = parts.split("-", 1)
                            task_id = id_part.strip()
                            title = title_part.strip()
                            break

                # Alternative: look for ID: pattern
                if "ID:" in line:
                    task_id = line.split("ID:")[1].strip().split()[0]

            if task_id:
                logger.info(f"Found next task: {task_id}")
                # Get full task details
                return await self.get_task(task_id)
            else:
                logger.warning("Could not parse task ID from output")
                logger.debug(f"Output was: {output[:500]}")

        except Exception as e:
            logger.error(f"Failed to parse next task: {e}")

        return None

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get details for a specific task."""
        output = await self._run_command("show", task_id)

        if output.startswith("Error:"):
            logger.error(f"Failed to get task {task_id}: {output}")
            return None

        try:
            # Parse task output
            # task-master show returns structured info
            lines = output.split('\n')

            task_data = {
                'id': task_id,
                'title': '',
                'description': '',
                'status': 'pending',
                'priority': None,
                'dependencies': []
            }

            for line in lines:
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if 'title' in key:
                        task_data['title'] = value
                    elif 'description' in key or 'details' in key:
                        task_data['description'] = value
                    elif 'status' in key:
                        task_data['status'] = value
                    elif 'priority' in key:
                        task_data['priority'] = value

            return Task(**task_data)

        except Exception as e:
            logger.error(f"Failed to parse task details: {e}")
            return None

    async def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        """List all tasks, optionally filtered by status."""
        args = ["list"]
        if status:
            args.extend(["--status", status])

        output = await self._run_command(*args)

        if output.startswith("Error:"):
            logger.error(f"Failed to list tasks: {output}")
            return []

        tasks = []
        in_table = False

        for line in output.split('\n'):
            # Skip decoration lines (box drawing characters)
            if '─' in line or '│' not in line:
                continue

            # Look for table rows with │ separators
            if '│' in line:
                # This is a table row
                parts = [p.strip() for p in line.split('│') if p.strip()]

                # Need at least ID and Title
                if len(parts) >= 2:
                    # First column should be ID
                    potential_id = parts[0]

                    # Check if it's a valid task ID (number or number.number)
                    if potential_id.replace('.', '').isdigit():
                        task_id = potential_id
                        title = parts[1] if len(parts) > 1 else ""
                        status_str = parts[2] if len(parts) > 2 else "pending"
                        priority = parts[3] if len(parts) > 3 else None

                        # Parse status (remove emoji/symbols)
                        status = "pending"
                        if "✓" in status_str or "done" in status_str.lower():
                            status = "done"
                        elif "○" in status_str or "pending" in status_str.lower():
                            status = "pending"
                        elif "◐" in status_str or "progress" in status_str.lower():
                            status = "in-progress"

                        # Only add if not a header row
                        if "Title" not in title and "ID" not in task_id:
                            tasks.append(Task(
                                id=task_id,
                                title=title,
                                description="",
                                status=status,
                                priority=priority if priority and priority != "Priority" else None
                            ))

        logger.info(f"Parsed {len(tasks)} tasks from output")
        return tasks

    async def set_status(self, task_id: str, status: str) -> bool:
        """Set the status of a task."""
        output = await self._run_command("set-status", f"--id={task_id}", f"--status={status}")

        if output.startswith("Error:"):
            logger.error(f"Failed to set status for {task_id}: {output}")
            return False

        logger.info(f"Task {task_id} status set to {status}")
        return True

    async def mark_complete(self, task_id: str) -> bool:
        """Mark a task as complete."""
        return await self.set_status(task_id, "done")

    async def mark_in_progress(self, task_id: str) -> bool:
        """Mark a task as in progress."""
        return await self.set_status(task_id, "in-progress")

    def set_working_directory(self, directory: str):
        """Change the working directory."""
        self.working_dir = directory
        logger.info(f"TaskMaster working directory set to: {directory}")
