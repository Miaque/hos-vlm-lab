import asyncio
import json

import httpx
import pytest

from hos_vlm_lab.config import ModelConfig
from hos_vlm_lab.gateway import Gateway


def model(identity="one"):
    return ModelConfig(identity, identity, "https://example.test/v1/chat/completions", "sk-test-private-credential", identity, "test")


@pytest.mark.asyncio
async def test_wire_body_exact_after_sdk_serialization_and_headers_redacted():
    sent = []
    response_body = '{"choices":[{"message":{"content":"{\\"events\\":[]}"},"finish_reason":"stop"}],"usage":{"prompt_tokens":123,"completion_tokens":9}}'

    def handler(request):
        sent.append(request)
        return httpx.Response(200, content=response_body, headers={"x-request-id": "upstream-123", "set-cookie": "private-session", "x-api-key": "unrelated-secret"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Gateway(client).call(model(), [b"full", b"tile"], "真实提示词\n第二行", {"enable_thinking": False, "max_tokens": 73}, {})
    assert len(sent) == 1
    assert result["request_body"] == sent[0].content.decode()
    body = json.loads(result["request_body"])
    assert body["model"] == "one"
    assert body["enable_thinking"] is False
    assert body["max_tokens"] == 73
    assert len(body["messages"][0]["content"]) == 3
    assert result["raw_response"] == response_body
    assert result["request_http"]["url"] == str(sent[0].url)
    assert result["request_http"]["headers"]["authorization"] == "[REDACTED]"
    assert result["response_http"]["headers"]["set-cookie"] == "[REDACTED]"
    assert result["response_http"]["headers"]["x-api-key"] == "[REDACTED]"
    assert result["response_http"]["headers"]["x-request-id"] == "upstream-123"
    assert "sk-test-private-credential" not in json.dumps(result)


@pytest.mark.asyncio
async def test_concurrent_failure_and_success_do_not_mix_packets():
    async def handler(request):
        identity = json.loads(request.content)["model"]
        if identity == "slow":
            await asyncio.sleep(0.02)
            return httpx.Response(502, text="upstream unavailable")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"events":[]}'}, "finish_reason": "stop"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = Gateway(client)
        results = await asyncio.gather(*(gateway.call(model(name), b"image", name, {}, {}) for name in ("slow", "fast")))
    for name, result in zip(("slow", "fast"), results):
        body = json.loads(result["request_body"])
        assert body["model"] == name
        assert body["messages"][0]["content"][0]["text"] == name
    assert results[0]["response_http"]["status_code"] == 502
    assert results[0]["raw_response"] == "upstream unavailable"
    assert results[1]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_timeout_still_records_dispatched_request():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Gateway(client).call(model(), b"image", "prompt", {}, {})
    assert result["error"]["code"] == "timeout"
    assert json.loads(result["request_body"])["model"] == "one"
    assert result["raw_response"] is None
    assert "response_http" not in result
