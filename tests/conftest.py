import pytest

from .fakes import fake_config


@pytest.fixture
def config(tmp_path):
    return fake_config(tmp_path)


@pytest.fixture(autouse=True)
def forbid_default_network(monkeypatch):
    import socket

    original = socket.socket.connect

    def denied(sock, address):
        # Windows asyncio 用本机 socket pair 唤醒事件循环。
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original(sock, address)
        raise AssertionError("测试禁止真实出站网络；请显式使用 MockTransport")

    monkeypatch.setattr(socket.socket, "connect", denied)
