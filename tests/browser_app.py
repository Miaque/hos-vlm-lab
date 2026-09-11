"""仅测试用：uv run python -m tests.browser_app --data-dir .test-data/browser。"""

import argparse
import socket
import tempfile
from pathlib import Path

import uvicorn

from hos_vlm_lab.app import create_app
from .fakes import FakeGateway, fake_config, fake_parameters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    temporary = (
        tempfile.TemporaryDirectory(prefix="hos-vlm-browser-")
        if args.data_dir is None
        else None
    )
    data_dir = args.data_dir or Path(temporary.name)
    if args.data_dir and not data_dir.resolve().is_relative_to(
        (Path.cwd() / ".test-data").resolve()
    ):
        parser.error("持久测试目录必须位于本仓库 .test-data 内")
    original = socket.socket.connect

    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original(sock, address)
        raise RuntimeError("模拟工作台禁止出站网络")

    socket.socket.connect = local_connect
    try:
        uvicorn.run(
            create_app(fake_config(data_dir), FakeGateway(1), fake_parameters),
            host="127.0.0.1",
            port=8001,
        )
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
