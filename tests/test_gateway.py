import json

import httpx
import pytest

from hos_vlm_lab.config import ModelConfig
from hos_vlm_lab.gateway import Gateway


@pytest.mark.asyncio
async def test_first_response_exact_prompt_and_no_retry():
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(429, text="quota secret")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = Gateway(client)
        model = ModelConfig(
            "one", "one", "https://example.test/chat", "secret", "model", "test"
        )
        result = await gateway.call(
            model, b"same image", " prompt\n", {"max_tokens": 1}, {"person": "人员"}
        )
    assert len(captured) == 1
    assert captured[0]["messages"][0]["content"][0]["text"] == " prompt\n"
    assert "system" not in str(captured)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "http_429"
    assert "secret" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,status", [('{"events":[]}', "succeeded"), ("{}", "invalid_response")]
)
async def test_empty_and_invalid_distinct(text, status):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": text}, "finish_reason": "stop"}]
                },
            )
        )
    ) as client:
        result = await Gateway(client).call(
            ModelConfig("x", "x", "https://example.test", "sensitive", "x", "x"),
            b"image",
            "prompt",
            {},
            {},
        )
    assert result["status"] == status
    assert result["raw_response"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", ["[]", "null", '"text"', '{"usage":{"prompt_tokens":NaN}}']
)
async def test_malformed_envelope_isolated(body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))
    ) as client:
        result = await Gateway(client).call(
            ModelConfig("x", "x", "https://example.test", "secret", "x", "x"),
            b"i",
            "p",
            {},
            {},
        )
    assert result["status"] == "invalid_response"
    json.dumps(result, allow_nan=False)


@pytest.mark.asyncio
async def test_failure_retains_usage():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(429, json={"usage": {"prompt_tokens": 12}})
        )
    ) as client:
        result = await Gateway(client).call(
            ModelConfig("x", "x", "https://example.test", "secret", "x", "x"),
            b"i",
            "p",
            {},
            {},
        )
    assert result["usage"] == {"prompt_tokens": 12}


@pytest.mark.asyncio
async def test_timeout_and_truncated_are_not_retried():
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        result = await Gateway(client).call(
            ModelConfig("x", "x", "https://example.test", "secret", "x", "x"),
            b"i",
            "p",
            {},
            {},
        )
    assert len(calls) == 1 and result["error"]["code"] == "timeout"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": '{"events":[]}'},
                            "finish_reason": "length",
                        }
                    ]
                },
            )
        )
    ) as client:
        result = await Gateway(client).call(
            ModelConfig("x", "x", "https://example.test", "secret", "x", "x"),
            b"i",
            "p",
            {},
            {},
        )
    assert result["status"] == "invalid_response"


@pytest.mark.asyncio
async def test_json_escaped_credential_is_redacted():
    body = '{"choices":[{"message":{"content":"\\u0073ecret"},"finish_reason":"stop"}]}'
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))
    ) as client:
        result = await Gateway(client).call(
            ModelConfig("x", "x", "https://example.test", "secret", "x", "x"),
            b"i",
            "p",
            {},
            {},
        )
    assert result["model_text"] != "secret"
    assert "secret" not in json.dumps(json.loads(result["raw_response"]))
