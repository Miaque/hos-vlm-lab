"""一次 HTTP 调用，保留首次响应，不进行网络或格式重试。"""

import asyncio
import base64
import json
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from .models import _json, parse_events


def normalize_usage(raw):
    raw = raw if isinstance(raw, dict) else {}

    def count(value):
        return value if type(value) is int and value >= 0 else None

    def detail(key, field):
        return raw[key].get(field) if isinstance(raw.get(key), dict) else None

    return {
        "input": count(raw.get("prompt_tokens")),
        "output": count(raw.get("completion_tokens")),
        "reasoning": count(detail("completion_tokens_details", "reasoning_tokens")),
        "cache_read": count(
            raw.get(
                "prompt_cache_hit_tokens",
                detail("prompt_tokens_details", "cached_tokens"),
            )
        ),
    }


def calculate_cost(usage, price, timestamp):
    if not price:
        return None
    try:
        at = datetime.fromisoformat(timestamp)
        if not (
            datetime.fromisoformat(price["valid_from"])
            <= at
            < datetime.fromisoformat(price["valid_until"])
        ):
            return None
        if not price["currency"] or not price["source"]:
            return None
        incoming, outgoing, cache = usage["input"], usage["output"], usage["cache_read"]
        if incoming is None or outgoing is None:
            return None
        if "cache_read_per_million" in price:
            if cache is None or cache > incoming:
                return None
        else:
            cache = 0
        rates = [
            Decimal(price["input_per_million"]),
            Decimal(price["output_per_million"]),
            Decimal(price.get("cache_read_per_million", "0")),
        ]
        if any(not rate.is_finite() or rate < 0 for rate in rates):
            return None
        value = (
            (incoming - cache) * rates[0] + outgoing * rates[1] + cache * rates[2]
        ) / Decimal(1_000_000)
        return format(value.normalize(), "f")
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None


class Gateway:
    def __init__(self, client: httpx.AsyncClient, secrets=()):
        self.client = client
        self.secrets = secrets

    async def call(self, model, image, prompt, parameters, events):
        body = {
            "model": model.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64,"
                                + base64.b64encode(image).decode()
                            },
                        },
                    ],
                }
            ],
            **parameters,
        }
        result = {
            "status": "failed",
            "request_parameters": parameters,
            "raw_response": None,
            "model_text": None,
            "parsed_events": None,
            "usage": None,
            "cost": None,
            "error": None,
        }
        started = time.monotonic()
        try:
            async with asyncio.timeout(180):
                response = await self.client.post(
                    model.api_url,
                    headers={"Authorization": f"Bearer {model.api_key}"},
                    json=body,
                )
            keys = tuple(k for k in (*self.secrets, model.api_key) if k)

            def redact(value):
                if isinstance(value, str):
                    for key in keys:
                        value = value.replace(key, "[REDACTED]")
                elif isinstance(value, list):
                    value = [redact(v) for v in value]
                elif isinstance(value, dict):
                    value = {redact(k): redact(v) for k, v in value.items()}
                return value

            raw = redact(response.text)
            result["raw_response"] = raw
            try:
                data = _json(raw)
                if not isinstance(data, dict):
                    raise ValueError("响应根节点必须是对象")
                sanitized = redact(data)
                if sanitized != data:
                    data = sanitized
                    result["raw_response"] = json.dumps(
                        data, ensure_ascii=False, allow_nan=False
                    )
                result["usage"] = data.get("usage")
            except ValueError:
                data = None
            if not response.is_success:
                result["error"] = {
                    "code": f"http_{response.status_code}",
                    "message": f"提供方 HTTP {response.status_code}",
                }
                return result
            result["status"] = "invalid_response"
            if data is None:
                raise ValueError("响应不符合 JSON 对象协议")
            choice = data["choices"][0]
            result["model_text"] = choice["message"]["content"]
            if choice.get("finish_reason") == "length":
                raise ValueError("模型输出被截断")
            result["parsed_events"] = parse_events(result["model_text"], events)
            result["status"] = "succeeded"
        except (TimeoutError, httpx.TimeoutException):
            result["error"] = {"code": "timeout", "message": "模型调用超时"}
        except httpx.HTTPError:
            result["error"] = {"code": "network", "message": "模型网络请求失败"}
        except (ValueError, KeyError, IndexError, TypeError):
            result["error"] = {
                "code": "invalid_response",
                "message": "首次响应不符合事件协议，详见原文",
            }
        finally:
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        return result
