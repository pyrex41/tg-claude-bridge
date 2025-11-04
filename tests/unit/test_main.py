import pytest
from main import require_auth, start_command, handle_message, run_agent_command
from unittest.mock import Mock, patch, AsyncMock

def test_require_auth(mock_update, mock_context):
    # Test authorized (simplified sync wrapper for test)
    def test_func(u, c): return 'ok'
    result = require_auth(test_func)(mock_update, mock_context)
    assert result == 'ok'

@pytest.mark.asyncio
async def test_start_command(mock_update, mock_context):
    with patch('main.logger') as mock_log:
        await start_command(mock_update, mock_context)
        mock_update.message.reply_text.assert_called()

@pytest.mark.asyncio
@patch('main.subprocess.Popen')
async def test_run_agent_command(mock_popen, mock_update, mock_context):
    prompt = 'test prompt'
    process = run_agent_command(prompt, 'agent')
    assert process == mock_popen.return_value
    mock_popen.assert_called_once()

@pytest.mark.asyncio
async def test_handle_message_agent_mode(mock_update, mock_context, mock_subprocess):
    with patch('main.active_mode', 'agent'):
        with patch('main.run_agent_with_auto_continue') as mock_run:
            await handle_message(mock_update, mock_context)
            mock_run.assert_called_once()
