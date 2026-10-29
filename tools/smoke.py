"""Start real HTTP servers on temporary ports; verify API and Streamlit startup."""

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(url: str, process: subprocess.Popen) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Server exited before becoming ready")
        try:
            if httpx.get(url, timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Server startup timed out")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="opspilot-http-") as directory:
        api_port, ui_port = port(), port()
        token = secrets.token_urlsafe(32)
        env = {**os.environ, "OPSPILOT_DATA_DIR": directory, "OPSPILOT_API_TOKEN": token}
        processes = []
        with (Path(directory) / "servers.log").open("w") as log:
            try:
                from opspilot.demo import seed
                from opspilot.retrieval import KnowledgeBase
                from opspilot.store import Store

                store = Store(Path(directory) / "opspilot.sqlite")
                seed(store, Path(directory) / "kb")
                KnowledgeBase(store).index(Path(directory) / "kb")
                api = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "opspilot.api.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                    ],
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                processes.append(api)
                base = f"http://127.0.0.1:{api_port}"
                wait_for(base + "/health", api)
                with httpx.Client(
                    base_url=base, headers={"Authorization": f"Bearer {token}"}
                ) as client:
                    response = client.post(
                        "/api/v1/tickets/analyze",
                        json={
                            "title": "VPN certificate expired",
                            "description": "VPN certificate expired today",
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    assert result["status"] == "pending"
                    approved = client.post(
                        f"/api/v1/investigations/{result['id']}/approve", json={}
                    )
                    approved.raise_for_status()
                    assert approved.json()["status"] == "completed"
                ui = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "streamlit",
                        "run",
                        "apps/dashboard.py",
                        "--server.headless",
                        "true",
                        "--server.address",
                        "127.0.0.1",
                        "--server.port",
                        str(ui_port),
                        "--browser.gatherUsageStats",
                        "false",
                    ],
                    env={**env, "OPSPILOT_API_URL": base},
                    stdout=log,
                    stderr=log,
                )
                processes.append(ui)
                wait_for(f"http://127.0.0.1:{ui_port}/_stcore/health", ui)
                print("PASS: real HTTP analysis, approval and Streamlit startup")
            finally:
                for process in reversed(processes):
                    process.terminate()
                    process.wait(timeout=15)


if __name__ == "__main__":
    main()
