from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

os.environ["RUNNER_SHARED_SECRET"] = "test-runner-secret-0123456789abcdef"

import app.main as runner_main
from app.main import (
    MAX_SCRIPT_LOG_BYTES,
    WRAPPER,
    ExecuteRequest,
    SandboxLimits,
    _sandbox_command,
    _sandbox_environment,
    python_for_packages,
)


def test_package_arguments_cannot_inject_installer_options_or_urls() -> None:
    base = {"code": "def fetch(payload): return {}", "payload": {}}
    for package in ("--index-url", "https://evil.example/pkg.whl", "name @ https://evil.example"):
        with pytest.raises(ValidationError):
            ExecuteRequest(**base, packages=[package])

    request = ExecuteRequest(**base, packages=["httpx>=0.28,<1"])
    assert request.packages == ["httpx>=0.28,<1"]


def test_sandbox_command_drops_identity_and_applies_resource_limits() -> None:
    command = _sandbox_command(
        ["python", "source.py"],
        user="runner-exec",
        limits=SandboxLimits(memory_bytes=128_000_000, cpu_seconds=30, processes=32),
    )
    assert command[0] == "prlimit"
    assert "--as=128000000" in command
    assert "--cpu=30" in command
    assert "--nproc=32" in command
    assert "--fsize=1048576" in command
    assert "--nofile=128" in command
    assert "setpriv" in command
    assert "--reuid=runner-exec" in command
    assert "--clear-groups" in command
    assert "--no-new-privs" in command
    assert command[-2:] == ["python", "source.py"]


def test_sandbox_environment_does_not_expose_runner_secret() -> None:
    environment = _sandbox_environment()
    assert "RUNNER_SHARED_SECRET" not in environment
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"


def test_package_environment_clears_the_precreated_staging_directory(
    monkeypatch, tmp_path
) -> None:
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runner_main, "cache_root", tmp_path)
    monkeypatch.setattr(runner_main, "_chown", lambda *args: None)
    monkeypatch.setattr(runner_main, "_seal_environment", lambda *args: None)
    monkeypatch.setattr(runner_main, "_run_sandboxed", fake_run)

    python_path = python_for_packages(["httpx"])

    assert commands[0][:3] == ["uv", "venv", "--clear"]
    assert commands[1][:4] == ["uv", "pip", "install", "--python"]
    assert python_path.name == "python"


def test_timeout_kills_process_group_and_escaped_user_processes(monkeypatch) -> None:
    events = []

    class FakeProcess:
        pid = 123
        returncode = -9

        def communicate(self, *, input, timeout):
            raise subprocess.TimeoutExpired(["python"], timeout)

        def wait(self):
            events.append("wait")

    process = FakeProcess()
    monkeypatch.setattr(runner_main.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        runner_main, "_terminate_process_group", lambda current: events.append("group")
    )
    monkeypatch.setattr(
        runner_main, "_terminate_user_processes", lambda user: events.append(f"user:{user}")
    )

    with pytest.raises(subprocess.TimeoutExpired):
        runner_main._run_sandboxed(
            ["python", "source.py"],
            user="runner-exec",
            limits=SandboxLimits(),
            timeout=1,
        )

    assert events == ["group", "wait", "group", "user:runner-exec"]


def test_wrapper_bounds_captured_script_output(tmp_path) -> None:
    source = tmp_path / "source.py"
    wrapper = tmp_path / "wrapper.py"
    source.write_text(
        "def fetch(payload):\n    print('x' * 400000)\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    wrapper.write_text(WRAPPER, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-I", str(wrapper), str(source), "fetch"],
        input="{}",
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["result"] == {"ok": True}
    assert len(payload["logs"].encode()) <= MAX_SCRIPT_LOG_BYTES
