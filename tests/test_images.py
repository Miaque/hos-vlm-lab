from io import BytesIO

import pytest
from PIL import Image

from hos_vlm_lab.images import prepare_images
from hos_vlm_lab.models import LabError


def png(size=(32, 16), mode="RGBA"):
    stream = BytesIO()
    Image.new(mode, size).save(stream, "PNG")
    return stream.getvalue()


def test_preparation_same_bytes_and_white_alpha(tmp_path):
    records = prepare_images([("../picture.png", png())], tmp_path)
    item = records[0]
    assert (item["width"], item["height"]) == (32, 16)
    assert item["original_name"] == "picture.png"
    prepared = Image.open(tmp_path / item["prepared_path"])
    assert prepared.getpixel((0, 0)) == (255, 255, 255)
    second = prepare_images([("other.png", png())], tmp_path)[0]
    assert item["prepared_sha256"] == second["prepared_sha256"]


def test_resize_without_upscale(tmp_path):
    item = prepare_images([("large.png", png((3000, 1500)))], tmp_path)[0]
    assert (item["width"], item["height"]) == (2048, 1024)


@pytest.mark.parametrize(
    "files",
    [[], [("x", b"bad")], [("x", b"x" * (10 * 1024 * 1024 + 1))], [("x", b"")] * 21],
)
def test_limits(tmp_path, files):
    with pytest.raises(LabError):
        prepare_images(files, tmp_path)
    assert not list(tmp_path.rglob("*.jpg"))


def test_whole_batch_and_animation_rejected(tmp_path):
    with pytest.raises(LabError):
        prepare_images([("good.png", png()), ("bad.png", b"bad")], tmp_path)
    assert not list(tmp_path.rglob("*.jpg"))
    stream = BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        stream,
        "WEBP",
        save_all=True,
        append_images=[Image.new("RGB", (4, 4), "blue")],
        duration=100,
        loop=0,
    )
    with pytest.raises(LabError):
        prepare_images([("animated.webp", stream.getvalue())], tmp_path)


def test_exif_orientation_and_pixel_limit(tmp_path):
    stream = BytesIO()
    im = Image.new("RGB", (10, 20))
    exif = im.getexif()
    exif[274] = 6
    im.save(stream, "JPEG", exif=exif)
    item = prepare_images([("rotated.jpg", stream.getvalue())], tmp_path)[0]
    assert (item["width"], item["height"]) == (20, 10)
    with pytest.raises(LabError) as exc:
        prepare_images([("huge.png", png((5000, 4001), "1"))], tmp_path)
    assert exc.value.status == 413


def test_twenty_images_accepted(tmp_path):
    assert len(prepare_images([(f"{i}.png", png()) for i in range(20)], tmp_path)) == 20


def test_failed_write_cleans_temporary_file(tmp_path, monkeypatch):
    from pathlib import Path

    original = Path.write_bytes

    def fail(path, content):
        original(path, content[:5])
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", fail)
    with pytest.raises(OSError):
        prepare_images([("image.png", png())], tmp_path)
    assert list(tmp_path.rglob("*.tmp")) == []
