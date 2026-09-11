import asyncio

import pytest

from hos_vlm_lab.models import LabError, RoundRequest
from hos_vlm_lab.runner import Runner
from hos_vlm_lab.store import Store
from .fakes import FakeGateway, fake_parameters
from .test_contracts import PROMPT


@pytest.mark.asyncio
async def test_stop_then_retry_has_independent_cancel(config):
    store = Store(config.data_dir)
    await store.open()
    for i in ("a", "b"):
        (config.data_dir / i).write_bytes(b"image")
    await store.add_images([{"id": i, "prepared_path": i} for i in ("a", "b")])
    gateway = FakeGateway(0.04)
    runner = Runner(store, config, gateway, fake_parameters)
    rid = await runner.create(
        RoundRequest(
            request_id="r",
            image_ids=["a", "b"],
            model_keys=["failure"],
            prompt_text=PROMPT,
            controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
        )
    )
    while not gateway.calls:
        await asyncio.sleep(0.001)
    result = await runner.stop(rid)
    assert result["status"] == "stopping"
    await runner.task
    result = await runner.detail(rid)
    assert result["counts"] == {"failed": 1, "stopped": 1}
    failed = next(a for a in result["attempts"] if a["status"] == "failed")
    retry = await runner.retry(failed["id"], "retry")
    assert (await runner.detail(rid))["status"] == "running"
    assert await runner.retry(failed["id"], "retry") == retry
    await runner.task
    assert len(gateway.calls) == 2
    assert (await runner.detail(rid))["counts"] == {"failed": 2, "stopped": 1}
    assert (await runner.stop(rid))["status"] == "stopped"
    stopped = next(a for a in result["attempts"] if a["status"] == "stopped")
    with pytest.raises(LabError):
        await runner.retry(stopped["id"], "not-allowed")
    await runner.close()
    await store.close()


@pytest.mark.asyncio
async def test_stop_during_image_read_prevents_dispatch(config, monkeypatch):
    from hos_vlm_lab import runner as runner_module

    store = Store(config.data_dir)
    await store.open()
    await store.add_images([{"id": "a", "prepared_path": "a"}])
    reading = asyncio.Event()
    release = asyncio.Event()

    async def delayed_read(*args):
        reading.set()
        await release.wait()
        return b"image"

    monkeypatch.setattr(runner_module.asyncio, "to_thread", delayed_read)
    gateway = FakeGateway()
    runner = Runner(store, config, gateway, fake_parameters)
    rid = await runner.create(
        RoundRequest(
            request_id="read-stop",
            image_ids=["a"],
            model_keys=["detected"],
            prompt_text=PROMPT,
            controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
        )
    )
    await asyncio.wait_for(reading.wait(), 1)
    await runner.stop(rid)
    release.set()
    await runner.task
    assert gateway.calls == []
    assert (await runner.detail(rid))["counts"] == {"stopped": 1}
    await runner.close()
    await store.close()


@pytest.mark.asyncio
async def test_retry_identity_change_rejected_and_second_stop(config):
    from dataclasses import replace

    store = Store(config.data_dir)
    await store.open()
    (config.data_dir / "a").write_bytes(b"image")
    await store.add_images([{"id": "a", "prepared_path": "a"}])
    gateway = FakeGateway(0.03)
    runner = Runner(store, config, gateway, fake_parameters)
    rid = await runner.create(
        RoundRequest(
            request_id="identity",
            image_ids=["a"],
            model_keys=["failure"],
            prompt_text=PROMPT,
            controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
        )
    )
    await runner.task
    old = (await runner.detail(rid))["attempts"][0]
    runner.config = replace(
        config, models=tuple(replace(m, model_id="changed") for m in config.models)
    )
    with pytest.raises(LabError) as exc:
        await runner.retry(old["id"], "changed")
    assert exc.value.status == 409
    runner.config = config
    await runner.retry(old["id"], "again")
    while len(gateway.calls) < 2:
        await asyncio.sleep(0.001)
    assert (await runner.stop(rid))["status"] == "stopping"
    await runner.task
    result = await runner.detail(rid)
    assert result["status"] == "completed"
    assert result["counts"] == {"failed": 2}
    await runner.close()
    await store.close()
