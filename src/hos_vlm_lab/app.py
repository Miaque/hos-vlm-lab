"""本机单进程工作台入口。"""

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import build_parameters, load_config
from .gateway import Gateway
from .images import MAX_BYTES, prepare_images
from .models import Controls, LabError, RetryRequest, RoundRequest
from .runner import Runner
from .store import Store

PACKAGE = Path(__file__).parent


def create_app(config=None, gateway=None, parameter_builder=build_parameters):
    config = config or load_config()

    @asynccontextmanager
    async def lifespan(app):
        store = Store(config.data_dir)
        await store.open()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180, connect=10),
            verify=False,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            runner = Runner(
                store,
                config,
                gateway or Gateway(client, tuple(m.api_key for m in config.models)),
                parameter_builder,
            )
            app.state.store, app.state.runner = store, runner
            try:
                yield
            finally:
                await runner.close()
                await store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def local_only(request, call_next):
        host = request.headers.get("host", "")
        try:
            hostname = urlsplit("http://" + host).hostname
        except ValueError:
            hostname = None
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            return JSONResponse(
                {"error": {"code": "invalid_host", "message": "仅允许本机访问"}},
                status_code=400,
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (
                origin and origin != f"{request.url.scheme}://{host}"
            ) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"error": {"code": "cross_origin", "message": "禁止跨源写入"}},
                    status_code=403,
                )
        return await call_next(request)

    @app.exception_handler(LabError)
    async def domain_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": str(exc), "details": exc.details}},
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # 不返回验证器的原始 input，避免不可信请求中的敏感文本回显。
        errors = [
            {"field": ".".join(map(str, e["loc"][1:])), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            {
                "error": {
                    "code": "validation",
                    "message": "输入校验失败",
                    "details": errors,
                }
            },
            status_code=422,
        )

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "storage",
                    "message": "本地存储操作失败，请检查目录与磁盘后重试",
                    "details": [],
                }
            },
            status_code=500,
        )

    @app.get("/api/config")
    async def configuration():
        models = []
        for model in config.models:
            reason = None
            try:
                parameter_builder(
                    model, Controls(thinking=False, max_tokens=1000, temperature=0.6)
                )
            except LabError as exc:
                reason = str(exc)
            models.append(
                {
                    "key": model.key,
                    "label": model.label,
                    "configured": bool(
                        model.api_key and model.api_url and model.model_id
                    ),
                    "runnable": reason is None,
                    "reason": reason,
                    "capabilities": {
                        "adapter": "langchain-openai",
                        "strict_validation": False,
                        "controls": {
                            "thinking": [False, True]
                            if model.key in {"qwen36", "qwen38", "qwen36_27b"}
                            else [False],
                            "thinking_budget": {"min": 1}
                            if model.key in {"qwen36", "qwen38", "qwen36_27b"}
                            else None,
                            "max_tokens": {"min": 1},
                            "temperature": {"min": 0, "max": 2},
                        }
                        if reason is None and not config.simulation
                        else None,
                        "source": "https://docs.langchain.com/oss/python/integrations/chat/openai"
                        if reason is None and not config.simulation
                        else None,
                    },
                }
            )
        return {
            "models": models,
            "simulation": config.simulation,
            "default_prompt": (PACKAGE / "default-prompt.json").read_text(
                encoding="utf-8"
            ),
            "limits": {
                "images": 20,
                "image_bytes": MAX_BYTES,
                "pixels": 20_000_000,
                "long_side": 2048,
            },
        }

    @app.post("/api/images", status_code=201)
    async def upload(files: list[UploadFile] = File(...)):
        try:
            if not 1 <= len(files) <= 20:
                raise LabError("每批须上传 1–20 张图片")
            content = []
            for file in files:
                raw = await file.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise LabError("单图不能超过 10 MiB", 413)
                content.append((file.filename or "image", raw))
            images = await asyncio.to_thread(prepare_images, content, config.data_dir)
            await app.state.store.add_images(images)
            return {"images": [public_image(i) for i in images]}
        finally:
            for file in files:
                await file.close()

    def public_image(item):
        return {
            k: v for k, v in item.items() if k not in {"original_path", "prepared_path"}
        } | {
            "name": item["original_name"],
            "original_url": f"/api/images/{item['id']}/original",
            "prepared_url": f"/api/images/{item['id']}/prepared",
        }

    @app.get("/api/images/{identity}/{variant}")
    async def image(identity: str, variant: str):
        if variant not in {"original", "prepared"}:
            raise LabError("图片版本不存在", 404)
        item = await app.state.store.image(identity)
        path = config.data_dir / item[variant + "_path"]
        if not path.is_file():
            raise LabError("本地图片文件缺失", 404)
        return FileResponse(
            path,
            media_type="image/jpeg"
            if variant == "prepared"
            else item.get("original_mime", "application/octet-stream"),
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.post("/api/rounds", status_code=202)
    async def create(body: RoundRequest):
        return {"round_id": await app.state.runner.create(body)}

    @app.get("/api/rounds")
    async def history(
        limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        result = await app.state.store.history(limit, offset)
        for item in result["items"]:
            if item["id"] == app.state.runner.round_id:
                item["status"] = (await app.state.runner.detail(item["id"]))["status"]
        return result

    @app.get("/api/rounds/{identity}")
    async def round_detail(identity: str):
        result = await app.state.runner.detail(identity)
        result["images"] = [public_image(i) for i in result["images"]]
        return result

    @app.get("/api/attempts/{identity}")
    async def attempt(identity: str):
        return await app.state.store.attempt(identity)

    @app.post("/api/rounds/{identity}/stop")
    async def stop(identity: str):
        result = await app.state.runner.stop(identity)
        return {
            "round_id": identity,
            "status": result["status"],
            "counts": result["counts"],
        }

    @app.post("/api/attempts/{identity}/retry", status_code=202)
    async def retry(identity: str, body: RetryRequest):
        return await app.state.runner.retry(identity, body.request_id)

    @app.get("/")
    async def index():
        return FileResponse(PACKAGE / "static/index.html")

    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
    return app
