import pytest
import sqlite3

from hos_vlm_lab.models import LabError
from hos_vlm_lab.store import Store


@pytest.mark.asyncio
async def test_atomic_round_and_idempotency(tmp_path):
    store = Store(tmp_path)
    await store.open()
    try:
        await store.add_images([{"id": "image"}])
        snapshot = {
            "request_id": "request",
            "image_ids": ["image"],
            "prompt_text": "exact text",
            "model_snapshot": [{"key": "one"}, {"key": "two"}],
            "controls": {},
        }
        first, created = await store.create_round(snapshot, {"one": {}, "two": {}})
        assert created
        assert len((await store.round(first))["attempts"]) == 2
        assert await store.create_round(snapshot, {"one": {}, "two": {}}) == (
            first,
            False,
        )
        with pytest.raises(LabError):
            await store.create_round(snapshot | {"prompt_text": "changed"}, {})
        with pytest.raises(sqlite3.IntegrityError):
            await store.create_round(
                snapshot | {"request_id": "bad", "image_ids": ["missing"]}, {}
            )
        assert (await store.history(20, 0))["total"] == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restart_interrupts_without_dispatch(tmp_path):
    store = Store(tmp_path)
    await store.open()
    await store.add_images([{"id": "image"}])
    rid, _ = await store.create_round(
        {"request_id": "r", "image_ids": ["image"], "model_snapshot": [{"key": "one"}]},
        {"one": {}},
    )
    await store.close()
    store = Store(tmp_path)
    await store.open()
    result = await store.round(rid)
    assert result["attempts"][0]["status"] == "interrupted"
    assert result["status"] == "completed"
    await store.close()
