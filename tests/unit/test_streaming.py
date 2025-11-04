import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from main import stream_output, read_process_lines

@pytest.mark.asyncio
@patch('main.application.bot.send_message')
async def test_stream_output(mock_send, mock_update):
    # Mock process with sample JSON lines
    mock_process = Mock()
    mock_process.stdout.readline = AsyncMock(side_effect=[
        json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Hello '}]}}).encode() + b'\n',
        json.dumps({'type': 'text', 'text': 'World!'}).encode() + b'\n',
        b''
    ])
    
    await stream_output(mock_process, Mock(), 98765, 'Agent', Mock())
    assert mock_send.called

@pytest.mark.asyncio
async def test_read_process_lines():
    mock_process = Mock()
    mock_process.stdout.readline = AsyncMock(return_value=b'line\n')
    lines = [line async for line in read_process_lines(mock_process)]
    assert len(lines) == 1
    assert lines[0] == 'line\n'
