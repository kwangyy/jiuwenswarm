"""AgentServer request failures must fail a voice task, not leave it unknown (#5885)."""

from types import SimpleNamespace

import pytest

from jiuwenswarm.extensions.video_duplex.backend import video_search
from jiuwenswarm.extensions.video_duplex.backend.tasks.service import ExecutionUncertain


def _client(*payloads):
    class Client:
        async def send_request_stream(self, _env):
            for payload in payloads:
                yield SimpleNamespace(payload=payload, is_complete=True)

    return Client()


@pytest.mark.asyncio
async def test_bare_server_error_fails_the_task_with_its_message():
    # AgentServer reports a failed request as {"error": ...} without event_type.
    # Ignoring it ended the stream without a final, which reads as "unknown"
    # (状态待核对) and hid the real cause from the user.
    client = _client({"error": "session has no active agent: chat-1"})

    with pytest.raises(RuntimeError, match="session has no active agent") as caught:
        await video_search.execute_core_agent(
            client, question="q", query="q", visual_context="", search_session_id="voice",
        )
    assert not isinstance(caught.value, ExecutionUncertain)


@pytest.mark.asyncio
async def test_typed_event_with_an_error_field_is_not_a_failure():
    # Only an untyped payload is a transport-level failure; typed events keep their meaning.
    client = _client(
        {"event_type": "chat.tool_result", "error": "tool said no"},
        {"event_type": "chat.final", "content": "Done"},
    )

    result = await video_search.execute_core_agent(
        client, question="q", query="q", visual_context="", search_session_id="voice",
    )
    assert result["raw_answer_chars"] == len("Done")
