"""统一预处理；先验证整批，再写入不可变图片文件。"""

import hashlib
import warnings
from math import ceil
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from .models import LabError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000


def detection_views(image: dict, tiled_codes: list[str], all_codes: list[str]) -> list[dict]:
    """沿用 hos-analysis 的宽图门槛、三片及 25% 重叠。坐标基于统一处理图。"""
    if not tiled_codes or image["width"] < image["height"] * 3:
        return []
    width, height = image["width"], image["height"]
    tile_width = ceil(width / 2.5)
    full_codes = [code for code in all_codes if code not in tiled_codes]
    views = ([{"id": "full", "bbox": None, "event_codes": full_codes}] if full_codes else [])
    for index in range(3):
        left = round(index * (width - tile_width) / 2)
        views.append({"id": f"T{index}", "bbox": [left, 0, left + tile_width, height], "event_codes": tiled_codes})
    return views


def encode_views(image: bytes, views: list[dict]) -> list[bytes]:
    with Image.open(BytesIO(image)) as source:
        result = []
        for view in views:
            if view["bbox"] is None:
                result.append(image)
            else:
                stream = BytesIO()
                source.crop(tuple(view["bbox"])).save(stream, "JPEG", quality=95)
                result.append(stream.getvalue())
        return result


def prepare_images(files: list[tuple[str, bytes]], data_dir: Path) -> list[dict]:
    if not 1 <= len(files) <= 20:
        raise LabError("每批须上传 1–20 张图片")
    validated = []
    for name, raw in files:
        if len(raw) > MAX_BYTES:
            raise LabError("单图不能超过 10 MiB", 413)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(raw)) as source:
                    if (
                        source.format not in {"JPEG", "PNG", "WEBP"}
                        or getattr(source, "n_frames", 1) != 1
                    ):
                        raise LabError("仅支持静态 JPEG、PNG、WebP")
                    if source.width * source.height > MAX_PIXELS:
                        raise LabError("单图解码像素不能超过 2000 万", 413)
                    source.load()
                    original_size = source.size
                    original_mime = Image.MIME[source.format]
                    oriented = ImageOps.exif_transpose(source).convert("RGBA")
                    rgb = Image.new("RGB", oriented.size, "white")
                    rgb.paste(oriented, mask=oriented.getchannel("A"))
                    rgb.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                    stream = BytesIO()
                    rgb.save(stream, "JPEG", quality=90)
                    prepared = stream.getvalue()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            if isinstance(exc, LabError):
                raise
            raise LabError("图片无法解码或超出限制") from exc
        identity = str(uuid4())
        record = {
            "id": identity,
            "original_name": name.replace("\\", "/").rsplit("/", 1)[-1],
            "original_sha256": hashlib.sha256(raw).hexdigest(),
            "prepared_sha256": hashlib.sha256(prepared).hexdigest(),
            "original_path": f"images/{identity}.original",
            "prepared_path": f"images/{identity}.jpg",
            "width": rgb.width,
            "height": rgb.height,
            "original_width": original_size[0],
            "original_height": original_size[1],
            "original_mime": original_mime,
            "preprocessing_version": "exif-white-rgb-2048-jpeg90-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        validated.append((record, raw, prepared))
    (data_dir / "images").mkdir(parents=True, exist_ok=True)
    for record, raw, prepared in validated:
        for field, content in (("original_path", raw), ("prepared_path", prepared)):
            target = data_dir / record[field]
            temporary = target.with_suffix(target.suffix + ".tmp")
            try:
                temporary.write_bytes(content)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    return [item[0] for item in validated]
