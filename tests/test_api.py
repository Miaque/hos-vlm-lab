from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from hos_vlm_lab.app import create_app
from .fakes import FakeGateway, fake_parameters
from .test_contracts import PROMPT


def test_upload_create_validation_and_secrets(config):
    gateway = FakeGateway()
    with TestClient(
        create_app(config, gateway, fake_parameters), base_url="http://127.0.0.1:8000"
    ) as client:
        response = client.get("/api/config")
        assert response.status_code == 200
        assert "test-only" not in response.text
        stream = BytesIO()
        Image.new("RGB", (20, 10)).save(stream, "PNG")
        response = client.post(
            "/api/images",
            files=[("files", ("image.png", stream.getvalue(), "image/png"))],
        )
        assert response.status_code == 201
        identity = response.json()["images"][0]["id"]
        payload = {
            "request_id": "r",
            "image_ids": [identity],
            "model_keys": ["detected", "empty"],
            "prompt_text": PROMPT,
            "controls": {"thinking": False, "temperature": 0.6, "max_tokens": 1000},
        }
        first = client.post("/api/rounds", json=payload)
        assert first.status_code == 202
        assert client.post("/api/rounds", json=payload).json() == first.json()
        assert (
            client.post(
                "/api/rounds", json=payload | {"prompt_text": PROMPT + " "}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/rounds",
                json=payload
                | {"request_id": "many", "image_ids": [str(i) for i in range(21)]},
            ).status_code
            == 422
        )
        assert client.get("/api/rounds?limit=0").status_code == 422
        assert client.get("/api/images/missing/prepared").status_code == 404
        assert (
            client.post(
                "/api/rounds", json=payload, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            client.get("/api/config", headers={"Host": "evil.example"}).status_code
            == 400
        )
        assert client.get("/api/rounds").json()["total"] == 1


def test_round_limit_cannot_be_bypassed_by_two_uploads(config):
    gateway = FakeGateway()
    with TestClient(
        create_app(config, gateway, fake_parameters), base_url="http://127.0.0.1:8000"
    ) as client:
        stream = BytesIO()
        Image.new("RGB", (2, 2)).save(stream, "PNG")
        ids = []
        for size in [20, 1]:
            response = client.post(
                "/api/images",
                files=[
                    ("files", (f"{i}.png", stream.getvalue(), "image/png"))
                    for i in range(size)
                ],
            )
            assert response.status_code == 201
            ids.extend(i["id"] for i in response.json()["images"])
        payload = {
            "request_id": "many",
            "image_ids": ids,
            "model_keys": ["detected"],
            "prompt_text": PROMPT,
            "controls": {"thinking": False, "max_tokens": 1000, "temperature": 0.6},
        }
        for image_ids in [[], ids]:
            assert (
                client.post(
                    "/api/rounds", json=payload | {"image_ids": image_ids}
                ).status_code
                == 422
            )
        assert client.get("/api/rounds").json()["total"] == 0
        assert gateway.calls == []
        assert (
            client.post(
                "/api/rounds", json=payload | {"image_ids": ids[:20]}
            ).status_code
            == 202
        )


def test_upload_failure_is_atomic_and_large_rejected(config):
    with TestClient(
        create_app(config, FakeGateway(), fake_parameters),
        base_url="http://127.0.0.1:8000",
    ) as client:
        stream = BytesIO()
        Image.new("RGB", (2, 2)).save(stream, "PNG")
        response = client.post(
            "/api/images",
            files=[
                ("files", ("ok.png", stream.getvalue())),
                ("files", ("bad.png", b"bad")),
            ],
        )
        assert response.status_code == 422
        assert not list(config.data_dir.rglob("*.jpg"))
        response = client.post(
            "/api/images",
            files=[("files", ("large.png", b"x" * (10 * 1024 * 1024 + 1)))],
        )
        assert response.status_code == 413


def test_stop_retry_api_and_identity_conflict(config):
    import time

    gateway = FakeGateway(0.01)
    with TestClient(
        create_app(config, gateway, fake_parameters), base_url="http://127.0.0.1:8000"
    ) as client:
        stream = BytesIO()
        Image.new("RGB", (2, 2)).save(stream, "PNG")
        image = client.post(
            "/api/images", files=[("files", ("ok.png", stream.getvalue()))]
        ).json()["images"][0]
        payload = {
            "request_id": "retry-round",
            "image_ids": [image["id"]],
            "model_keys": ["failure", "empty"],
            "prompt_text": PROMPT,
            "controls": {"thinking": False, "max_tokens": 1000, "temperature": 0.6},
        }
        rid = client.post("/api/rounds", json=payload).json()["round_id"]
        deadline = time.monotonic() + 3
        while True:
            round = client.get("/api/rounds/" + rid).json()
            if round["status"] == "completed":
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)
        failed = next(a for a in round["attempts"] if a["status"] == "failed")
        succeeded = next(a for a in round["attempts"] if a["status"] == "succeeded")
        path = "/api/attempts/" + failed["id"] + "/retry"
        response = client.post(path, json={"request_id": "retry-one"})
        assert response.status_code == 202
        assert (
            client.post(path, json={"request_id": "retry-one"}).json()
            == response.json()
        )
        assert (
            client.post(
                "/api/attempts/" + succeeded["id"] + "/retry",
                json={"request_id": "retry-one"},
            ).status_code
            == 409
        )
        assert client.post("/api/rounds/" + rid + "/stop").status_code == 200
        assert client.get("/api/attempts/missing").status_code == 404
        assert client.get("/api/images/%2e%2e/prepared").status_code == 404


def test_resource_cleanup_and_storage_errors_are_safe(config, monkeypatch):
    app = create_app(config, FakeGateway(), fake_parameters)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:

        async def broken(*args):
            raise OSError("test-only credential and internal path")

        monkeypatch.setattr(app.state.store, "image", broken)
        response = client.get("/api/images/a/prepared")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "storage"
        assert "test-only" not in response.text
    assert not app.state.runner.active
    import pytest

    with pytest.raises(RuntimeError):
        app.state.store.executor.submit(lambda: None)
