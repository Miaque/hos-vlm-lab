import pytest
from PIL import Image

from hos_vlm_lab.images import prepare_images
from hos_vlm_lab.store import Store


@pytest.mark.asyncio
async def test_history_files_and_pagination_survive_source_move(tmp_path):
    source = tmp_path / "source.png"
    image = Image.new("RGB", (5, 10))
    image.save(source)
    directory = tmp_path / "data"
    records = prepare_images([(source.name, source.read_bytes())], directory)
    store = Store(directory)
    await store.open()
    await store.add_images(records)
    rounds = []
    for i in range(3):
        rid, _ = await store.create_round(
            {
                "request_id": str(i),
                "image_ids": [records[0]["id"]],
                "model_snapshot": [{"key": "m"}],
                "prompt_text": f"prompt {i}",
            },
            {"m": {}},
        )
        rounds.append(rid)
    await store.close()
    source.rename(tmp_path / "moved.png")
    store = Store(directory)
    await store.open()
    page = await store.history(1, 1)
    assert page["total"] == 3
    assert page["items"][0]["id"] == rounds[1]
    record = await store.image(records[0]["id"])
    assert (directory / record["original_path"]).read_bytes() == (
        tmp_path / "moved.png"
    ).read_bytes()
    assert Image.open(directory / record["prepared_path"]).size == (5, 10)
    assert (await store.round(rounds[0]))["prompt_text"] == "prompt 0"
    await store.close()
