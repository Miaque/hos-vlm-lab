"""单活跃批次、每模型串行；全部预检及提交完成后才允许调用。"""

import asyncio
import time

from .config import build_parameters
from .models import LabError, parse_prompt
from .store import now
from .gateway import calculate_cost, normalize_usage
from .prompts import PROMPT_RENDERER_VERSION, render_prompt


class Runner:
    def __init__(self, store, config, gateway, parameter_builder=build_parameters):
        self.store, self.config, self.gateway = store, config, gateway
        self.parameter_builder = parameter_builder
        self.lock = asyncio.Lock()
        self.task = None
        self.round_id = None
        self.cancel_requested = False
        self.failure = None
        self.attempt_ids = []

    @property
    def active(self):
        return self.task is not None and not self.task.done()

    async def create(self, request):
        async with self.lock:
            prior = await self.store.find_request(request.request_id)
            payload = request.model_dump()
            if prior:
                if prior[1]["request"] != payload:
                    raise LabError("request_id 已用于不同内容", 409, "conflict")
                return prior[0]
            if self.active or self.failure:
                raise LabError("已有活动轮次或存储故障，请等待或重启检查", 409, "busy")
            selected = []
            parameters = {}
            errors = []
            for key in request.model_keys:
                model = next((m for m in self.config.models if m.key == key), None)
                if model is None:
                    raise LabError("模型不存在")
                try:
                    parameters[key] = self.parameter_builder(model, request.controls)
                except LabError as exc:
                    errors.append({"model_key": key, "message": str(exc)})
                selected.append(model)
            if errors:
                raise LabError("所选模型存在不兼容配置", details=errors)
            for identity in request.image_ids:
                await self.store.image(identity)
            snapshot = payload | {
                "request": payload,
                "rendered_prompt_text": render_prompt(request.prompt_text),
                "prompt_renderer_version": PROMPT_RENDERER_VERSION,
                "event_snapshot": parse_prompt(request.prompt_text),
                "model_snapshot": [m.identity() for m in selected],
                "pricing_snapshot": {m.key: m.pricing for m in selected},
            }
            rid, created = await self.store.create_round(snapshot, parameters)
            if created:
                self.round_id = rid
                self.cancel_requested = False
                self.attempt_ids = [
                    a["id"] for a in (await self.store.round(rid))["attempts"]
                ]
                self.task = asyncio.create_task(self._run(rid, selected))
            return rid

    async def _run(self, rid, selected):
        try:
            snapshot = await self.store.round(rid)

            async def model_worker(model):
                for attempt in snapshot["attempts"]:
                    if (
                        attempt["id"] not in self.attempt_ids
                        or attempt["model_key"] != model.key
                        or attempt["status"] != "queued"
                    ):
                        continue
                    image = await self.store.image(attempt["image_id"])
                    image_bytes = await asyncio.to_thread(
                        (self.config.data_dir / image["prepared_path"]).read_bytes
                    )
                    async with self.lock:
                        if self.cancel_requested or self.failure:
                            return
                        await self._save(attempt["id"], "running", started_at=now())
                    started = time.monotonic()
                    timestamp = now()
                    result = await self.gateway.call(
                        model,
                        image_bytes,
                        snapshot.get("rendered_prompt_text", snapshot["prompt_text"]),
                        attempt["request_parameters"],
                        snapshot["event_snapshot"],
                    )
                    result.setdefault(
                        "elapsed_ms", round((time.monotonic() - started) * 1000)
                    )
                    result["normalized_usage"] = normalize_usage(result.get("usage"))
                    price = snapshot.get("pricing_snapshot", {}).get(model.key)
                    result["pricing"] = price
                    result["cost"] = calculate_cost(
                        result["normalized_usage"], price, timestamp
                    )
                    result["currency"] = price.get("currency") if price else None
                    status = result.pop("status")
                    await self._save(attempt["id"], status, finished_at=now(), **result)

            # TaskGroup cancels siblings if persistence fails; no further dispatch follows.
            async with asyncio.TaskGroup() as group:
                for model in selected:
                    group.create_task(model_worker(model))
        except Exception:
            self.failure = "运行或存储故障；未完成项将在重启后标记中断"

    async def _save(self, *args, **kwargs):
        try:
            await self.store.update_attempt(*args, **kwargs)
        except Exception:
            self.failure = "存储写入失败，已停止新增调度；请重启检查"
            raise

    async def detail(self, rid):
        result = await self.store.round(rid)
        if (
            rid == self.round_id
            and self.active
            and self.cancel_requested
            and result["counts"].get("running")
        ):
            result["status"] = "stopping"
        if self.failure and rid == self.round_id:
            result["scheduler_error"] = self.failure
        return result

    async def stop(self, rid):
        async with self.lock:
            await self.store.round(rid)
            if self.active and self.round_id == rid:
                self.cancel_requested = True
                await self.store.stop_queued(rid, self.attempt_ids)
            return await self.detail(rid)

    async def retry(self, identity, request_id):
        async with self.lock:
            prior = await self.store.find_retry(request_id)
            if prior:
                if prior["retry_of"] != identity:
                    raise LabError("重试 request_id 已用于其他目标", 409)
                return {"round_id": prior["round_id"], "attempt_id": prior["id"]}
            if self.active or self.failure:
                raise LabError("已有活动批次或存储故障", 409)
            old = await self.store.attempt(identity)
            if old["status"] not in {"failed", "invalid_response", "interrupted"}:
                raise LabError("此尝试不可重试", 409)
            snapshot = await self.store.round(old["round_id"])
            model = next(
                (m for m in self.config.models if m.key == old["model_key"]), None
            )
            saved = next(
                m for m in snapshot["model_snapshot"] if m["key"] == old["model_key"]
            )
            if model is None or model.identity() != saved or not model.api_key:
                raise LabError("连接身份已改变或密钥缺失，请新建轮次", 409)
            aid = await self.store.append_retry(old, request_id)
            self.round_id = old["round_id"]
            self.cancel_requested = False
            self.attempt_ids = [aid]
            self.task = asyncio.create_task(self._run(self.round_id, [model]))
            return {"round_id": self.round_id, "attempt_id": aid}

    async def close(self):
        if self.active:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
