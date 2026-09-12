import asyncio

import pytest

from hos_vlm_lab.models import RoundRequest
from hos_vlm_lab.runner import Runner
from hos_vlm_lab.store import Store
from .fakes import FakeGateway, fake_parameters
from .test_contracts import PROMPT


@pytest.mark.asyncio
async def test_cartesian_inputs_and_snapshot(config):
    store = Store(config.data_dir)
    await store.open()
    for identity in ("a", "b"):
        (config.data_dir / identity).write_bytes(identity.encode())
    await store.add_images([{"id": i, "prepared_path": i} for i in ("a", "b")])
    gateway = FakeGateway(0.01)
    runner = Runner(store, config, gateway, fake_parameters)
    request = RoundRequest(
        request_id="r",
        image_ids=["a", "b"],
        model_keys=["detected", "empty"],
        prompt_text=PROMPT,
        controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
    )
    rid = await runner.create(request)
    assert await runner.create(request) == rid
    await runner.task
    assert len(gateway.calls) == 4
    snapshot = await store.round(rid)
    assert snapshot["prompt_text"] == PROMPT
    assert all(call[2] == snapshot["rendered_prompt_text"] for call in gateway.calls)
    assert (await store.round(rid))["counts"] == {"succeeded": 4}
    await runner.close()
    await store.close()


@pytest.mark.asyncio
async def test_per_model_serial_and_slow_isolation(config):
    from dataclasses import replace

    config = replace(config, models=(*config.models, replace(config.models[0], key="qwen36_27b")))
    store = Store(config.data_dir)
    await store.open()
    (config.data_dir / "a").write_bytes(b"image")
    await store.add_images([{"id": i, "prepared_path": "a"} for i in ("a", "b")])
    release = asyncio.Event()
    finished = asyncio.Event()
    all_started = asyncio.Event()
    running = set()
    maximum = 0
    calls = []

    class Gateway:
        async def call(self, model, *args):
            nonlocal maximum
            assert model.key not in running
            running.add(model.key)
            maximum = max(maximum, len(running))
            if len(running) == 5:
                all_started.set()
            await all_started.wait()
            if model.key == "slow":
                await release.wait()
            await asyncio.sleep(0.005)
            calls.append(model.key)
            running.remove(model.key)
            if calls.count("empty") == 2:
                finished.set()
            return {"status": "succeeded", "parsed_events": [], "usage": None}

    runner = Runner(store, config, Gateway(), fake_parameters)
    await runner.create(
        RoundRequest(
            request_id="concurrency",
            image_ids=["a", "b"],
            model_keys=[m.key for m in config.models],
            prompt_text=PROMPT,
            controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
        )
    )
    await asyncio.wait_for(finished.wait(), 1)
    assert "slow" not in calls
    assert maximum == 5
    release.set()
    await runner.task
    assert len(calls) == 10
    await runner.close()
    await store.close()


@pytest.mark.asyncio
async def test_transaction_failure_never_calls(config, monkeypatch):
    store = Store(config.data_dir)
    await store.open()
    await store.add_images([{"id": "a"}])
    gateway = FakeGateway()
    runner = Runner(store, config, gateway, fake_parameters)

    async def fail(*args):
        raise OSError("database unavailable")

    monkeypatch.setattr(store, "create_round", fail)
    with pytest.raises(OSError):
        await runner.create(
            RoundRequest(
                request_id="r",
                image_ids=["a"],
                model_keys=["detected"],
                prompt_text=PROMPT,
                controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
            )
        )
    assert not gateway.calls
    await runner.close()
    await store.close()


@pytest.mark.asyncio
async def test_result_persistence_failure_stops_dispatch(config, monkeypatch):
    store = Store(config.data_dir)
    await store.open()
    (config.data_dir / "a").write_bytes(b"image")
    await store.add_images([{"id": i, "prepared_path": "a"} for i in ["a", "b"]])
    original = store.update_attempt

    async def fail_result(identity, status, **detail):
        if status == "succeeded":
            raise OSError("disk full")
        await original(identity, status, **detail)

    monkeypatch.setattr(store, "update_attempt", fail_result)
    gateway = FakeGateway()
    runner = Runner(store, config, gateway, fake_parameters)
    rid = await runner.create(
        RoundRequest(
            request_id="write-fails",
            image_ids=["a", "b"],
            model_keys=["detected"],
            prompt_text=PROMPT,
            controls={"thinking": False, "max_tokens": 1000, "temperature": 0.6},
        )
    )
    await runner.task
    assert len(gateway.calls) == 1
    assert (await runner.detail(rid))["scheduler_error"]
    await runner.close()
    await store.close()
