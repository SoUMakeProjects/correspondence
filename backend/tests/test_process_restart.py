import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx


@contextmanager
def running_server(data_dir, port):
    environment = {
        **os.environ,
        "APP_DATA_DIR": str(data_dir),
        "AZURE_OPENAI_BASE_URL": "",
        "AZURE_OPENAI_DEPLOYMENT": "",
        "AZURE_OPENAI_API_KEY": "",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=2
        ) as client:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError("Foundation server exited before becoming healthy.")
                try:
                    if client.get("/api/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Foundation server did not become healthy.")
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_committed_case_and_event_survive_actual_server_restart(tmp_path, case_payload):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with running_server(tmp_path, port) as first:
        response = first.post("/api/cases", json=case_payload)
        assert response.status_code == 201
        item = response.json()
        events = first.get(f"/api/cases/{item['id']}/events").json()
    with running_server(tmp_path, port) as second:
        assert second.get(f"/api/cases/{item['id']}").json() == item
        assert second.get(f"/api/cases/{item['id']}/events").json() == events
