import pytest

from hos_vlm_lab.models import LabError, RoundRequest
from hos_vlm_lab.runner import Runner
from hos_vlm_lab.store import Store
from hos_vlm_lab.prompts import render_prompt
from .fakes import FakeGateway, fake_parameters


@pytest.mark.asyncio
async def test_exact_prompt_immutable_and_model_failure_preflight(config):
    store = Store(config.data_dir)
    await store.open()
    (config.data_dir / "image").write_bytes(b"image")
    await store.add_images([{"id": "image", "prepared_path": "image"}])
    gateway = FakeGateway(0.01)

    def validate(model, controls):
        if model.key == "failure":
            raise LabError("不兼容参数")
        return fake_parameters(model, controls)

    runner = Runner(store, config, gateway, validate)
    prompt = ' { "events" : [ {"code":"edited", "name":"修改后的场景"} ] } \n'
    request = RoundRequest(
        request_id="one",
        image_ids=["image"],
        model_keys=["detected", "failure"],
        prompt_text=prompt,
        controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
    )
    with pytest.raises(LabError):
        await runner.create(request)
    assert not gateway.calls
    assert (await store.history(20, 0))["total"] == 0
    request.model_keys = ["detected"]
    rid = await runner.create(request)
    request.prompt_text = '{"events": [{"code":"next","name":"下一轮"}]}'
    await runner.task
    assert gateway.calls[0][2] == render_prompt(prompt)
    assert (await store.round(rid))["rendered_prompt_text"] == gateway.calls[0][2]
    assert (await store.round(rid))["event_snapshot"] == {"edited": "修改后的场景"}
    request.request_id = "two"
    second = await runner.create(request)
    await runner.task
    assert (await store.round(rid))["prompt_text"] == prompt
    assert (await store.round(second))["prompt_text"] == request.prompt_text
    await runner.close()
    await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_retry_uses_frozen_text_after_restart(config, monkeypatch, legacy):
    from hos_vlm_lab import runner as module
    from hos_vlm_lab.store import dump

    store = Store(config.data_dir)
    await store.open()
    (config.data_dir / "image").write_bytes(b"image")
    await store.add_images([{"id": "image", "prepared_path": "image"}])
    gateway = FakeGateway()
    runner = Runner(store, config, gateway, fake_parameters)
    prompt = '{"events":[{"code":"a","name":"事件"}]}'
    rid = await runner.create(RoundRequest(request_id="r", image_ids=["image"], model_keys=["failure"], prompt_text=prompt, controls={"thinking": False, "max_tokens": 1000, "temperature": 0.0}))
    await runner.task
    saved = await store.round(rid)
    expected = saved["rendered_prompt_text"]
    if legacy:
        def downgrade():
            import json
            row = store.db.execute("SELECT snapshot FROM rounds WHERE id=?", (rid,)).fetchone()
            snapshot = json.loads(row[0])
            snapshot.pop("rendered_prompt_text")
            snapshot.pop("prompt_renderer_version")
            with store.db:
                store.db.execute("UPDATE rounds SET snapshot=? WHERE id=?", (dump(snapshot), rid))
        await store.call(downgrade)
        expected = prompt
    await runner.close()
    await store.close()
    store = Store(config.data_dir)
    await store.open()
    monkeypatch.setattr(module, "render_prompt", lambda _: "新版本不能影响历史")
    runner = Runner(store, config, gateway, fake_parameters)
    await runner.retry(saved["attempts"][0]["id"], "retry")
    await runner.task
    assert gateway.calls[-1][2] == expected
    await runner.close()
    await store.close()
