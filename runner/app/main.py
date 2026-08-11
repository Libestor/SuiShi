from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator


PACKAGE_SPEC_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(?:\[[A-Za-z0-9._,-]+\])?"
    r"(?:(?:===|==|~=|!=|<=|>=|<|>)[A-Za-z0-9.*+!_-]+"
    r"(?:,(?:===|==|~=|!=|<=|>=|<|>)[A-Za-z0-9.*+!_-]+)*)?$"
)
PUBLIC_RUNNER_SECRETS = {"dev-runner-secret", "replace-with-a-long-random-runner-secret"}
RUNNER_BUILDER_USER = os.environ.get("RUNNER_BUILDER_USER", "runner-builder")
RUNNER_EXEC_USER = os.environ.get("RUNNER_EXEC_USER", "runner-exec")
MAX_CAPTURE_BYTES = 1_048_576
MAX_SCRIPT_LOG_BYTES = 262_144


@dataclass(frozen=True)
class SandboxLimits:
    memory_bytes: int = 536_870_912
    cpu_seconds: int = 60
    processes: int = 64
    file_size_bytes: int = MAX_CAPTURE_BYTES
    open_files: int = 128


class ExecuteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=500_000)
    function_name: str = Field(default="fetch", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    payload: dict[str, Any]
    packages: list[str] = Field(default_factory=list, max_length=100)
    timeout_seconds: int = Field(default=30, ge=1, le=60)

    @field_validator("packages")
    @classmethod
    def validate_packages(cls, packages: list[str]) -> list[str]:
        normalized = []
        for package in packages:
            value = package.strip()
            if not value or len(value) > 200 or not PACKAGE_SPEC_PATTERN.fullmatch(value):
                raise ValueError(
                    "packages must be registry package names with optional version constraints"
                )
            normalized.append(value)
        return normalized


app = FastAPI(title="Investment Overview Python Runner", version="0.1.0")
shared_secret = os.environ.get("RUNNER_SHARED_SECRET", "").strip()
if len(shared_secret) < 32 or shared_secret in PUBLIC_RUNNER_SECRETS:
    raise RuntimeError("RUNNER_SHARED_SECRET must be an explicit non-development secret")
cache_root = Path(os.environ.get("RUNNER_CACHE_DIR", "/runner-cache"))
max_timeout = int(os.environ.get("RUNNER_MAX_TIMEOUT_SECONDS", "60"))
_environment_lock = Lock()
_execution_lock = Lock()


def require_secret(x_runner_secret: str | None = Header(default=None)) -> None:
    if not x_runner_secret or not secrets.compare_digest(x_runner_secret, shared_secret):
        raise HTTPException(status_code=401, detail="Invalid runner secret")


def _sandbox_environment(home: str = "/tmp") -> dict[str, str]:
    return {
        "HOME": home,
        "LANG": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


def _sandbox_command(
    command: list[str], *, user: str, limits: SandboxLimits
) -> list[str]:
    return [
        "prlimit",
        f"--as={limits.memory_bytes}",
        f"--cpu={limits.cpu_seconds}",
        f"--nproc={limits.processes}",
        f"--fsize={limits.file_size_bytes}",
        f"--nofile={limits.open_files}",
        "--core=0",
        "--",
        "setpriv",
        f"--reuid={user}",
        f"--regid={user}",
        "--clear-groups",
        "--no-new-privs",
        "--",
        *command,
    ]


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _terminate_user_processes(user: str) -> None:
    """Reap descendants that deliberately escaped the job process group."""
    account = pwd.getpwnam(user)
    proc_root = Path("/proc")
    if not proc_root.exists():
        return
    for _ in range(5):
        matched = False
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != account.pw_uid:
                    continue
                os.kill(int(entry.name), signal.SIGKILL)
                matched = True
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        if not matched:
            break


def _run_sandboxed(
    command: list[str],
    *,
    user: str,
    limits: SandboxLimits,
    timeout: int,
    input_text: str | None = None,
    cwd: Path | None = None,
    home: str = "/tmp",
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            _sandbox_command(command, user=user, limits=limits),
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            cwd=cwd,
            env=_sandbox_environment(home),
            start_new_session=True,
        )
        try:
            process.communicate(
                input=input_text.encode() if input_text is not None else None,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process)
            process.wait()
            raise subprocess.TimeoutExpired(command, timeout) from exc
        finally:
            _terminate_process_group(process)
            _terminate_user_processes(user)

        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(MAX_CAPTURE_BYTES + 1).decode(errors="replace")
        stderr = stderr_file.read(MAX_CAPTURE_BYTES + 1).decode(errors="replace")
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _chown(path: Path, user: str) -> None:
    account = pwd.getpwnam(user)
    os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)


def _seal_environment(path: Path) -> None:
    for item in sorted(path.rglob("*"), reverse=True):
        if item.is_symlink():
            os.chown(item, 0, 0, follow_symlinks=False)
            continue
        mode = 0o555 if item.is_dir() or item.stat().st_mode & stat.S_IXUSR else 0o444
        os.chown(item, 0, 0)
        os.chmod(item, mode)
    os.chown(path, 0, 0)
    os.chmod(path, 0o555)


def python_for_packages(packages: list[str]) -> Path:
    if not packages:
        return Path(sys.executable)
    normalized = sorted(set(package.strip() for package in packages if package.strip()))
    digest = hashlib.sha256("\n".join(normalized).encode()).hexdigest()[:20]
    env_dir = cache_root / "envs" / digest
    python_path = env_dir / "bin" / "python"
    with _environment_lock:
        if python_path.exists():
            return python_path

        env_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_root = cache_root / "staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = staging_root / f"{digest}-{secrets.token_hex(8)}"
        staging.mkdir(mode=0o700)
        _chown(staging, RUNNER_BUILDER_USER)
        staging_python = staging / "bin" / "python"
        limits = SandboxLimits(
            cpu_seconds=180,
            file_size_bytes=536_870_912,
            open_files=256,
        )
        try:
            create = _run_sandboxed(
                ["uv", "venv", str(staging)],
                user=RUNNER_BUILDER_USER,
                limits=limits,
                timeout=60,
                cwd=staging,
                home=str(staging),
            )
            if create.returncode != 0:
                raise RuntimeError(create.stderr[-4000:] or "Failed to create package environment")
            install = _run_sandboxed(
                ["uv", "pip", "install", "--python", str(staging_python), "--", *normalized],
                user=RUNNER_BUILDER_USER,
                limits=limits,
                timeout=180,
                cwd=staging,
                home=str(staging),
            )
            if install.returncode != 0:
                raise RuntimeError(install.stderr[-4000:] or "Failed to install packages")
            _seal_environment(staging)
            os.replace(staging, env_dir)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return python_path


WRAPPER = r'''
import contextlib
import importlib.util
import json
import sys

MAX_LOG_BYTES = __MAX_SCRIPT_LOG_BYTES__

class BoundedTextCapture:
    def __init__(self, limit):
        self.limit = limit
        self.size = 0
        self.chunks = []

    def write(self, value):
        encoded = value.encode("utf-8", errors="replace")
        remaining = self.limit - self.size
        if remaining > 0:
            chunk = encoded[:remaining]
            self.chunks.append(chunk)
            self.size += len(chunk)
        return len(value)

    def flush(self):
        return None

    def getvalue(self):
        return b"".join(self.chunks).decode("utf-8", errors="replace")

source_path, function_name = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("user_source", source_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
payload = json.load(sys.stdin)
captured = BoundedTextCapture(MAX_LOG_BYTES)
with contextlib.redirect_stdout(captured):
    result = function(payload)
if not isinstance(result, dict):
    raise TypeError("Data source function must return a dict")
print(json.dumps({"result": result, "logs": captured.getvalue()}, ensure_ascii=False, default=str))
'''.replace("__MAX_SCRIPT_LOG_BYTES__", str(MAX_SCRIPT_LOG_BYTES))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "investment-overview-runner"}


@app.post("/execute")
def execute(
    request: ExecuteRequest,
    x_runner_secret: str | None = Header(default=None, alias="X-Runner-Secret"),
) -> dict[str, Any]:
    require_secret(x_runner_secret)
    timeout = min(request.timeout_seconds, max_timeout)
    try:
        with _execution_lock:
            python_path = python_for_packages(request.packages)
            with tempfile.TemporaryDirectory(prefix="investment-source-") as temp_dir:
                temp = Path(temp_dir)
                source_file = temp / "source.py"
                wrapper_file = temp / "wrapper.py"
                source_file.write_text(request.code, encoding="utf-8")
                wrapper_file.write_text(WRAPPER, encoding="utf-8")
                os.chmod(temp, 0o700)
                _chown(temp, RUNNER_EXEC_USER)
                for file in (source_file, wrapper_file):
                    os.chmod(file, 0o400)
                    _chown(file, RUNNER_EXEC_USER)
                result = _run_sandboxed(
                    [
                        str(python_path),
                        "-I",
                        str(wrapper_file),
                        str(source_file),
                        request.function_name,
                    ],
                    user=RUNNER_EXEC_USER,
                    limits=SandboxLimits(cpu_seconds=timeout),
                    timeout=timeout,
                    input_text=json.dumps(request.payload, ensure_ascii=False),
                    cwd=temp,
                    home=str(temp),
                )
        if result.returncode != 0:
            raise HTTPException(status_code=422, detail=result.stderr[-4000:] or "Script failed")
        payload = json.loads(result.stdout)
        return {"status": "success", **payload}
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=408, detail=f"Script exceeded {timeout}s timeout") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:4000]) from exc
