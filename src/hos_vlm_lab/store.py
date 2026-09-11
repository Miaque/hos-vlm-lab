"""单工作线程拥有 SQLite 连接；快照与任务在同一短事务中提交。"""

import asyncio
import hashlib
import json
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import LabError


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="vlm-sqlite"
        )

    async def call(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(
            self.executor, fn, *args
        )

    async def open(self):
        def initialize():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.data_dir / "lab.sqlite3")
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS images (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rounds (
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
                    snapshot TEXT NOT NULL, created_at TEXT NOT NULL, stop_requested INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS round_images (
                    round_id TEXT REFERENCES rounds(id), image_id TEXT REFERENCES images(id), position INTEGER NOT NULL,
                    PRIMARY KEY(round_id,image_id));
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES rounds(id),
                    image_id TEXT NOT NULL REFERENCES images(id), model_key TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL, retry_of TEXT REFERENCES attempts(id), retry_request_id TEXT UNIQUE,
                    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','invalid_response','failed','stopped','interrupted')),
                    snapshot TEXT NOT NULL, UNIQUE(round_id,image_id,model_key,attempt_no));
            """)
            with self.db:
                self.db.execute(
                    "UPDATE attempts SET status='interrupted' WHERE status IN ('queued','running')"
                )

        await self.call(initialize)

    async def close(self):
        await self.call(self.db.close)
        self.executor.shutdown(wait=True)

    async def add_images(self, images):
        def write():
            with self.db:
                self.db.executemany(
                    "INSERT INTO images VALUES (?,?)",
                    [(i["id"], dump(i)) for i in images],
                )

        await self.call(write)

    async def image(self, identity):
        def read():
            row = self.db.execute(
                "SELECT snapshot FROM images WHERE id=?", (identity,)
            ).fetchone()
            if row is None:
                raise LabError("图片不存在", 404, "not_found")
            return json.loads(row[0])

        return await self.call(read)

    async def find_request(self, request_id):
        def read():
            row = self.db.execute(
                "SELECT id,snapshot FROM rounds WHERE request_id=?", (request_id,)
            ).fetchone()
            return (row[0], json.loads(row[1])) if row else None

        return await self.call(read)

    async def create_round(self, snapshot, parameters):
        def write():
            fingerprint = hashlib.sha256(dump(snapshot).encode()).hexdigest()
            with self.db:
                prior = self.db.execute(
                    "SELECT id,request_hash FROM rounds WHERE request_id=?",
                    (snapshot["request_id"],),
                ).fetchone()
                if prior:
                    if prior[1] != fingerprint:
                        raise LabError("request_id 已用于不同内容", 409, "conflict")
                    return prior[0], False
                rid = str(uuid4())
                self.db.execute(
                    "INSERT INTO rounds(id,request_id,request_hash,snapshot,created_at) VALUES (?,?,?,?,?)",
                    (rid, snapshot["request_id"], fingerprint, dump(snapshot), now()),
                )
                for position, image_id in enumerate(snapshot["image_ids"]):
                    self.db.execute(
                        "INSERT INTO round_images VALUES (?,?,?)",
                        (rid, image_id, position),
                    )
                    for model in snapshot["model_snapshot"]:
                        detail = {
                            "request_parameters": parameters[model["key"]],
                            "created_at": now(),
                            "raw_response": None,
                            "parsed_events": None,
                            "error": None,
                            "usage": None,
                            "cost": None,
                            "currency": None,
                        }
                        self.db.execute(
                            "INSERT INTO attempts(id,round_id,image_id,model_key,attempt_no,status,snapshot) VALUES (?,?,?,?,1,'queued',?)",
                            (str(uuid4()), rid, image_id, model["key"], dump(detail)),
                        )
                return rid, True

        return await self.call(write)

    def _attempt(self, row):
        result = dict(row)
        result.update(json.loads(result.pop("snapshot")))
        return result

    async def attempt(self, identity):
        def read():
            row = self.db.execute(
                "SELECT * FROM attempts WHERE id=?", (identity,)
            ).fetchone()
            if not row:
                raise LabError("尝试不存在", 404, "not_found")
            return self._attempt(row)

        return await self.call(read)

    async def update_attempt(self, identity, status, **detail):
        def write():
            with self.db:
                row = self.db.execute(
                    "SELECT snapshot FROM attempts WHERE id=?", (identity,)
                ).fetchone()
                if not row:
                    raise LabError("尝试不存在", 404, "not_found")
                snapshot = json.loads(row[0]) | detail
                self.db.execute(
                    "UPDATE attempts SET status=?,snapshot=? WHERE id=?",
                    (status, dump(snapshot), identity),
                )

        await self.call(write)

    async def round(self, identity):
        def read():
            row = self.db.execute(
                "SELECT * FROM rounds WHERE id=?", (identity,)
            ).fetchone()
            if not row:
                raise LabError("轮次不存在", 404, "not_found")
            result = json.loads(row["snapshot"]) | {
                "id": row["id"],
                "created_at": row["created_at"],
                "stop_requested": bool(row["stop_requested"]),
            }
            result["images"] = [
                json.loads(i[0])
                for i in self.db.execute(
                    "SELECT i.snapshot FROM round_images r JOIN images i ON r.image_id=i.id WHERE r.round_id=? ORDER BY r.position",
                    (identity,),
                )
            ]
            attempts = [
                self._attempt(a)
                for a in self.db.execute(
                    "SELECT * FROM attempts WHERE round_id=? ORDER BY rowid",
                    (identity,),
                )
            ]
            result["attempts"] = [
                {
                    k: v
                    for k, v in a.items()
                    if k not in {"raw_response", "model_text", "request_body"}
                }
                for a in attempts
            ]
            counts = dict(Counter(a["status"] for a in attempts))
            result["counts"] = counts
            result["status"] = (
                "running"
                if counts.get("queued", 0) + counts.get("running", 0)
                else ("stopped" if counts.get("stopped") else "completed")
            )
            return result

        return await self.call(read)

    async def history(self, limit, offset):
        def read():
            rows = self.db.execute(
                "SELECT id FROM rounds ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = self.db.execute("SELECT count(*) FROM rounds").fetchone()[0]
            return [row[0] for row in rows], total

        identities, total = await self.call(read)
        items = []
        for identity in identities:
            result = await self.round(identity)
            items.append(
                {key: result[key] for key in ("id", "created_at", "status", "counts")}
            )
        return {"items": items, "total": total}

    async def stop_queued(self, rid, identities):
        def write():
            with self.db:
                self.db.execute("UPDATE rounds SET stop_requested=1 WHERE id=?", (rid,))
                self.db.executemany(
                    "UPDATE attempts SET status='stopped' WHERE id=? AND status='queued'",
                    [(i,) for i in identities],
                )

        await self.call(write)

    async def find_retry(self, request_id):
        def read():
            row = self.db.execute(
                "SELECT * FROM attempts WHERE retry_request_id=?", (request_id,)
            ).fetchone()
            return self._attempt(row) if row else None

        return await self.call(read)

    async def append_retry(self, old, request_id):
        def write():
            with self.db:
                number = self.db.execute(
                    "SELECT max(attempt_no)+1 FROM attempts WHERE round_id=? AND image_id=? AND model_key=?",
                    (old["round_id"], old["image_id"], old["model_key"]),
                ).fetchone()[0]
                identity = str(uuid4())
                snapshot = {
                    "request_parameters": old["request_parameters"],
                    "created_at": now(),
                    "pricing": old.get("pricing"),
                    "raw_response": None,
                    "parsed_events": None,
                    "error": None,
                    "usage": None,
                    "cost": None,
                    "currency": None,
                }
                self.db.execute(
                    "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,'queued',?)",
                    (
                        identity,
                        old["round_id"],
                        old["image_id"],
                        old["model_key"],
                        number,
                        old["id"],
                        request_id,
                        dump(snapshot),
                    ),
                )
                return identity

        return await self.call(write)
