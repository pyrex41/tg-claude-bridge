import pytest
import sys
from unittest.mock import Mock, patch
sys.path.insert(0, '../')

@pytest.fixture
def mock_update():
    update = Mock()
    update.effective_user.id = 12345  # Allowed ID
    update.effective_chat.id = 98765
    update.message = Mock()
    update.message.text = 'test'
    update.message.reply_text = Mock()
    return update

@pytest.fixture
def mock_context():
    context = Mock()
    context.application = Mock()
    context.application.bot = Mock()
    context.application.bot.send_message = Mock()
    context.args = []
    return context

@pytest.fixture
@patch('subprocess.Popen')
def mock_subprocess(pop):
    pop.return_value = Mock()
    pop.return_value.stdout.readline.return_value = ''
    pop.return_value.poll.return_value = 0
    return pop

@pytest.fixture
@patch('mcp.client.stdio.stdio_client')  # For MCP version
def mock_mcp(mcp):
    mock_session = Mock()
    mock_result = Mock()
    mock_result.content = [Mock(text='{"action": "continue", "prompt": "test", "reasoning": "ok"}')]
    mock_session.call_tool.return_value = mock_result
    mcp.return_value.__aenter__.return_value = (Mock(), Mock(), mock_session)
    return mcp
