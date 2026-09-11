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


@pytest.mark.asyncio
@pytest.mark.parametrize("thinking", [False, True])
async def test_langchain_independent_connections_and_raw_responses(monkeypatch, thinking):
    import asyncio
    import base64
    from hos_vlm_lab.config import build_parameters, load_config
    from hos_vlm_lab.models import Controls

    monkeypatch.setenv("VLM_BASE_URL", "https://shared.test/proxy/v1/")
    monkeypatch.setenv("VLM_API_KEY", "shared-key")
    monkeypatch.setenv("QWEN36_27B_BASE_URL", "https://independent.test/v1")
    monkeypatch.setenv("QWEN36_27B_API_KEY", "independent-key")
    monkeypatch.setenv("QWEN36_MODEL_ID", "qwen3.6-flash")
    monkeypatch.setenv("QWEN36_27B_MODEL_ID", "qwen3.6-27b")
    models = [m for m in load_config().models if m.key in {"qwen36", "qwen36_27b"}]
    captured = []

    async def handler(request):
        body = json.loads(request.content)
        captured.append((str(request.url), request.headers["authorization"], body))
        await asyncio.sleep(0.01 if request.url.host == "shared.test" else 0)
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 1, "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"events":[]}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15, "prompt_cache_hit_tokens": 4},
            "provider_extension": body["model"],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = Gateway(client)
        parameters = [build_parameters(m, Controls(thinking=thinking, thinking_budget=100 if thinking else None, max_tokens=1000, temperature=0.6)) for m in models]
        results = await asyncio.gather(*(gateway.call(m, b"same image", " original prompt\n", p, {}) for m, p in zip(models, parameters)))
    assert len(captured) == 2
    assert {(url, auth) for url, auth, _ in captured} == {
        ("https://shared.test/proxy/v1/chat/completions", "Bearer shared-key"),
        ("https://independent.test/v1/chat/completions", "Bearer independent-key"),
    }
    for (_, _, body), parameter in zip(captured, parameters):
        assert {k: body[k] for k in parameter} == parameter
        assert ("max_completion_tokens" in body) is thinking
        assert "extra_body" not in body
        assert ("thinking_budget" in body) is thinking
        assert body["messages"] == [{"role": "user", "content": [
            {"type": "text", "text": " original prompt\n"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b"same image").decode()}},
        ]}]
    for model, result in zip(models, results):
        assert result["status"] == "succeeded"
        assert json.loads(result["raw_response"])["provider_extension"] == model.model_id
        assert result["usage"]["prompt_cache_hit_tokens"] == 4
