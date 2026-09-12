import base64
import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from hos_vlm_lab.gateway import Gateway
from hos_vlm_lab.images import detection_views, encode_views, prepare_images
from hos_vlm_lab.models import RoundRequest, parse_prompt
from hos_vlm_lab.runner import Runner
from hos_vlm_lab.store import Store
from .fakes import FakeGateway, fake_parameters
from .test_images import png


def test_views_geometry_and_opt_in():
    wide = {"width": 300, "height": 100}
    assert detection_views(wide, [], ["garbage"]) == []
    assert detection_views({"width": 299, "height": 100}, ["garbage"], ["garbage"]) == []
    views = detection_views(wide, ["garbage"], ["garbage", "person"])
    assert views[0] == {"id": "full", "bbox": None, "event_codes": ["person"]}
    assert [view["bbox"] for view in views[1:]] == [[0, 0, 120, 100], [90, 0, 210, 100], [180, 0, 300, 100]]
    image = Image.new("RGB", (300, 100))
    for x in range(300):
        image.paste((x % 256, 20, 10), (x, 0, x + 1, 100))
    stream = BytesIO()
    image.save(stream, "JPEG")
    encoded = encode_views(stream.getvalue(), views)
    assert encoded[0] == stream.getvalue()
    assert [Image.open(BytesIO(item)).size for item in encoded[1:]] == [(120, 100)] * 3
    assert len(set(encoded[1:])) == 3
    assert [view["id"] for view in detection_views(wide, ["garbage"], ["garbage"])] == ["T0", "T1", "T2"]


@pytest.mark.parametrize("value", [1, "true", None, []])
def test_tile_switch_rejects_non_boolean(value):
    with pytest.raises(ValueError, match="tile_detection"):
        parse_prompt(json.dumps({"events": [{"code": "g", "name": "垃圾", "tile_detection": value}]}))


@pytest.mark.asyncio
async def test_frozen_inputs_shared_across_models_and_retry(config, monkeypatch):
    store = Store(config.data_dir)
    await store.open()
    images = prepare_images([("wide.png", png((300, 100))), ("normal.png", png((100, 100)))], config.data_dir)
    await store.add_images(images)
    gateway = FakeGateway()
    runner = Runner(store, config, gateway, fake_parameters)
    try:
        request = RoundRequest(
            request_id="tiles", image_ids=[i["id"] for i in images], model_keys=["empty", "failure"],
            prompt_text=json.dumps({"events": [{"code": "g", "name": "垃圾", "tile_detection": True}, {"code": "p", "name": "人员"}]}),
            controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
        )
        rid = await runner.create(request)
        await runner.task
        assert runner.failure is None
        saved = await store.round(rid)
        wide_input = saved["image_detection_inputs"][images[0]["id"]]
        assert len(wide_input["views"]) == 4
        assert "不跨片拼凑证据" in wide_input["prompt"]
        assert saved["image_detection_inputs"][images[1]["id"]]["views"] == []
        wide_calls = [call for call in gateway.calls if isinstance(call[1], list)]
        assert len(wide_calls) == 2
        assert wide_calls[0][1:3] == wide_calls[1][1:3]
        assert all(a["detection_input"] for a in saved["attempts"])
        failed = next(a for a in saved["attempts"] if a["status"] == "failed" and a["image_id"] == images[0]["id"])
        monkeypatch.setattr("hos_vlm_lab.runner.render_view_prompt", lambda *args: pytest.fail("重试不得重新编排"))
        await runner.retry(failed["id"], "retry-tiles")
        await runner.task
        assert gateway.calls[-1][1:3] == wide_calls[0][1:3]
        assert await runner.create(request) == rid
    finally:
        await runner.close()
        await store.close()


@pytest.mark.asyncio
async def test_multi_view_one_request_preserves_usage_and_errors(config):
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 123, "completion_tokens": 9}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Gateway(client).call(config.models[0], [b"full", b"T0", b"T1", b"T2"], "frozen", {}, {"g": "垃圾"})
    assert len(captured) == 1
    content = captured[0]["messages"][0]["content"]
    assert content[0]["text"] == "frozen"
    assert [base64.b64decode(part["image_url"]["url"].split(",")[1]) for part in content[1:]] == [b"full", b"T0", b"T1", b"T2"]
    assert result["status"] == "invalid_response"
    assert result["usage"] == {"prompt_tokens": 123, "completion_tokens": 9}
