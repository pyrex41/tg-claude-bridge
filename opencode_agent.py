"""
OpenCode CLI Integration
Wrapper for calling opencode CLI programmatically
"""

import asyncio
import json
import logging
from typing import Optional, Dict, List, Callable, Awaitable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OpenCodeResponse:
    """Response from OpenCode CLI."""
    content: str
    session_id: Optional[str] = None
    model: Optional[str] = None
    tool_calls: List[Dict] = None
    events: List[Dict] = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []
        if self.events is None:
            self.events = []


@dataclass
class OpenCodeEvent:
    """Parsed event from OpenCode stream."""
    type: str
    message: str
    data: Optional[Dict] = None


class OpenCodeAgent:
    """Wrapper for OpenCode CLI operations."""

    def __init__(self, model: str = "grok-4-non-reasoning", working_dir: str = "."):
        self.model = model
        self.working_dir = working_dir
        self.session_id: Optional[str] = None

    def parse_event(self, event: Dict) -> Optional[OpenCodeEvent]:
        """Parse a JSON event into a human-readable message."""
        event_type = event.get('type', '')

        # Text content - full text, no truncation (caller will handle display)
        if event_type == 'text':
            part = event.get('part', {})
            text = part.get('text', '')
            if text:
                return OpenCodeEvent(type='text', message=text, data=event)

        # Tool use
        elif event_type == 'tool_use':
            part = event.get('part', {})
            tool_name = part.get('tool', 'unknown')
            state = part.get('state', {})
            status = state.get('status', '')

            # Clean up tool names
            clean_name = tool_name.replace('task-master-ai_', '').replace('_', ' ').title()

            if status == 'completed':
                return OpenCodeEvent(
                    type='tool',
                    message=f"🔧 Used: {clean_name}",
                    data=event
                )
            else:
                return OpenCodeEvent(
                    type='tool',
                    message=f"🔧 Using: {clean_name}...",
                    data=event
                )

        # Step start/finish
        elif event_type == 'step_start':
            return OpenCodeEvent(type='step', message="🚀 Starting step...", data=event)

        elif event_type == 'step_finish':
            part = event.get('part', {})
            reason = part.get('reason', '')
            cost = part.get('cost', 0)
            tokens = part.get('tokens', {})

            if reason == 'stop':
                msg = f"✅ Step complete"
                if cost:
                    msg += f" (${cost:.4f})"
                return OpenCodeEvent(type='step', message=msg, data=event)

        # File edits
        elif event_type == 'file_edit' or event_type == 'file.edited':
            part = event.get('part', {})
            file_path = part.get('path', 'file')
            return OpenCodeEvent(type='file', message=f"📝 Edited: {file_path}", data=event)

        # Errors
        elif event_type == 'error':
            error = event.get('error', {})
            msg = error.get('message', 'Unknown error')
            return OpenCodeEvent(type='error', message=f"❌ Error: {msg}", data=event)

        return None

    async def run(
        self,
        prompt: str,
        continue_session: bool = False,
        files: List[str] = None,
        event_callback: Optional[Callable[[OpenCodeEvent], Awaitable[None]]] = None
    ) -> OpenCodeResponse:
        """
        Run opencode with a prompt.

        Args:
            prompt: The prompt to send
            continue_session: Whether to continue the last session
            files: Optional list of files to attach

        Returns:
            OpenCodeResponse with content and metadata
        """
        cmd = ["opencode", "run"]

        # Add flags
        if continue_session and self.session_id:
            cmd.extend(["--session", self.session_id])

        cmd.extend(["--model", self.model])
        cmd.extend(["--format", "json"])  # Get JSON output

        # Add files
        if files:
            for file in files:
                cmd.extend(["--file", file])

        # Add prompt
        cmd.append(prompt)

        logger.info(f"Running OpenCode: {' '.join(cmd[:5])}...")

        try:
            # Run command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"OpenCode error: {error_msg}")
                return OpenCodeResponse(
                    content=f"Error: {error_msg}",
                    model=self.model
                )

            # Parse JSON output
            output = stdout.decode()

            # OpenCode JSON format: stream of JSON events
            # We need to collect all content and events
            content_parts = []
            tool_calls = []
            all_events = []
            session_id = None

            for line in output.strip().split('\n'):
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)
                    all_events.append(event)

                    # Parse and send event via callback
                    parsed_event = self.parse_event(event)
                    if parsed_event and event_callback:
                        await event_callback(parsed_event)

                    # Extract session ID
                    if 'sessionID' in event:
                        session_id = event['sessionID']

                    # Extract text content
                    if event.get('type') == 'text':
                        part = event.get('part', {})
                        text = part.get('text', '')
                        if text:
                            content_parts.append(text)

                    # Track tool calls
                    elif event.get('type') == 'tool_use':
                        tool_calls.append(event)

                except json.JSONDecodeError:
                    # Not JSON, might be direct text output
                    logger.warning(f"Failed to parse JSON line: {line[:100]}")
                    content_parts.append(line)

            # Combine content
            final_content = '\n'.join(content_parts) if content_parts else "No response content"

            # Store session ID for continuation
            if session_id:
                self.session_id = session_id

            logger.info(f"OpenCode response ({len(final_content)} chars, {len(all_events)} events)")

            return OpenCodeResponse(
                content=final_content.strip(),
                session_id=session_id,
                model=self.model,
                tool_calls=tool_calls,
                events=all_events
            )

        except Exception as e:
            logger.error(f"OpenCode execution error: {e}")
            return OpenCodeResponse(
                content=f"Execution error: {e}",
                model=self.model
            )

    async def clear_session(self):
        """Clear the current session."""
        self.session_id = None
        logger.info("OpenCode session cleared")

    def set_working_directory(self, directory: str):
        """Change the working directory."""
        self.working_dir = directory
        logger.info(f"Working directory set to: {directory}")
