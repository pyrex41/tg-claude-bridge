"""
Task Master CLI Integration
Client for interacting with task-master CLI
"""

import asyncio
import json
import logging
import os
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

    async def _run_command(self, *args, timeout: int = 10) -> str:
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

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"task-master command timed out after {timeout}s")
                process.kill()
                await process.wait()
                return f"Error: Command timed out after {timeout}s"

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"task-master error: {error_msg[:500]}")
                return f"Error: {error_msg[:500]}"

            return stdout.decode().strip()

        except FileNotFoundError:
            logger.error("task-master CLI not found")
            return "Error: task-master CLI not installed"
        except Exception as e:
            logger.error(f"task-master execution error: {e}")
            return f"Error: {e}"

    async def get_next_task(self) -> Optional[Task]:
        """Get the next available task to work on."""
        # Try reading from JSON first (much faster and more reliable)
        try:
            tasks = await self.list_tasks(status="pending")

            # Find first task with no dependencies or all dependencies done
            tasks_file = os.path.join(self.working_dir, ".taskmaster", "tasks", "tasks.json")
            if os.path.exists(tasks_file):
                import json
                with open(tasks_file, 'r') as f:
                    data = json.load(f)

                    # Get all task data
                    all_tasks = {}
                    for tag_name, tag_data in data.items():
                        if isinstance(tag_data, dict) and 'tasks' in tag_data:
                            for task_data in tag_data['tasks']:
                                all_tasks[str(task_data.get('id'))] = task_data

                    # Find tasks that are ready (no dependencies or deps are done)
                    for task in tasks:
                        task_data = all_tasks.get(task.id)
                        if not task_data:
                            continue

                        deps = task_data.get('dependencies', [])
                        if not deps:
                            # No dependencies, ready to work on
                            logger.info(f"Found next task: {task.id} (no dependencies)")
                            return task

                        # Check if all dependencies are done
                        all_deps_done = all(
                            all_tasks.get(str(dep), {}).get('status') == 'done'
                            for dep in deps
                        )

                        if all_deps_done:
                            logger.info(f"Found next task: {task.id} (dependencies met)")
                            return task

            # If no tasks found with met dependencies, just return first pending
            if tasks:
                logger.info(f"Returning first pending task: {tasks[0].id}")
                return tasks[0]

            logger.info("No pending tasks found")
            return None

        except Exception as e:
            logger.warning(f"Could not get next task from JSON: {e}, falling back to CLI")

        # Fallback to CLI (which may be broken)
        output = await self._run_command("next")

        if output.startswith("Error:"):
            logger.error(f"Failed to get next task: {output}")
            return None

        if "no task" in output.lower() or "all tasks complete" in output.lower():
            logger.info("No tasks available")
            return None

        return None

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get details for a specific task."""
        # Try reading from JSON first
        try:
            tasks_file = os.path.join(self.working_dir, ".taskmaster", "tasks", "tasks.json")
            if os.path.exists(tasks_file):
                import json
                with open(tasks_file, 'r') as f:
                    data = json.load(f)

                    # Find task in any tag
                    for tag_name, tag_data in data.items():
                        if isinstance(tag_data, dict) and 'tasks' in tag_data:
                            for task_data in tag_data['tasks']:
                                if str(task_data.get('id')) == str(task_id):
                                    logger.info(f"Found task {task_id} in JSON")
                                    return Task(
                                        id=str(task_data.get('id', '')),
                                        title=task_data.get('title', ''),
                                        description=task_data.get('description', ''),
                                        status=task_data.get('status', 'pending'),
                                        priority=task_data.get('priority'),
                                        dependencies=task_data.get('dependencies', [])
                                    )

            logger.warning(f"Task {task_id} not found in JSON")
        except Exception as e:
            logger.warning(f"Could not read task from JSON: {e}")

        # Fallback to CLI
        output = await self._run_command("show", task_id)

        if output.startswith("Error:"):
            logger.error(f"Failed to get task {task_id}: {output}")
            return None

        return None

    async def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        """List all tasks, optionally filtered by status."""
        # Try reading tasks.json directly first (much faster)
        try:
            tasks_file = os.path.join(self.working_dir, ".taskmaster", "tasks", "tasks.json")
            if os.path.exists(tasks_file):
                import json
                with open(tasks_file, 'r') as f:
                    data = json.load(f)
                    tasks = []

                    # Handle tagged structure (e.g., {"master": {...}, "viral": {...}})
                    task_list = []
                    if 'tasks' in data:
                        # Direct tasks array
                        task_list = data['tasks']
                    else:
                        # Tagged structure - get all tasks from all tags
                        for tag_name, tag_data in data.items():
                            if isinstance(tag_data, dict) and 'tasks' in tag_data:
                                task_list.extend(tag_data['tasks'])

                    for task_data in task_list:
                        # Filter by status if specified
                        if status and task_data.get('status') != status:
                            continue

                        tasks.append(Task(
                            id=str(task_data.get('id', '')),
                            title=task_data.get('title', ''),
                            description=task_data.get('description', ''),
                            status=task_data.get('status', 'pending'),
                            priority=task_data.get('priority'),
                            dependencies=task_data.get('dependencies', [])
                        ))

                    logger.info(f"Loaded {len(tasks)} tasks from tasks.json")
                    return tasks
        except Exception as e:
            logger.warning(f"Could not read tasks.json directly: {e}, falling back to CLI")

        # Fallback to CLI if direct read fails
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
        # Write directly to JSON (CLI is broken/slow)
        try:
            tasks_file = os.path.join(self.working_dir, ".taskmaster", "tasks", "tasks.json")
            if os.path.exists(tasks_file):
                import json

                # Read current data
                with open(tasks_file, 'r') as f:
                    data = json.load(f)

                # Find and update task in any tag
                found = False
                for tag_name, tag_data in data.items():
                    if isinstance(tag_data, dict) and 'tasks' in tag_data:
                        for task_data in tag_data['tasks']:
                            if str(task_data.get('id')) == str(task_id):
                                task_data['status'] = status
                                found = True
                                break
                        if found:
                            break

                if found:
                    # Write back to file
                    with open(tasks_file, 'w') as f:
                        json.dump(data, f, indent=2)

                    logger.info(f"Task {task_id} status set to {status} (JSON direct)")
                    return True
                else:
                    logger.error(f"Task {task_id} not found in JSON")
                    return False

        except Exception as e:
            logger.error(f"Failed to set status in JSON: {e}")

        # Fallback to CLI (will likely timeout)
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
