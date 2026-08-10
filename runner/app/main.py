from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=500_000)
    function_name: str = Field(default="fetch", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    payload: dict[str, Any]
    packages: list[str] = Field(default_factory=list, max_length=100)
    timeout_seconds: int = Field(default=30, ge=1, le=60)


app = FastAPI(title="Investment Overview Python Runner", version="0.1.0")
shared_secret = os.environ.get("RUNNER_SHARED_SECRET", "dev-runner-secret")
cache_root = Path(os.environ.get("RUNNER_CACHE_DIR", "/runner-cache"))
max_timeout = int(os.environ.get("RUNNER_MAX_TIMEOUT_SECONDS", "60"))


def require_secret(x_runner_secret: str | None = Header(default=None)) -> None:
    if not x_runner_secret or not secrets.compare_digest(x_runner_secret, shared_secret):
        raise HTTPException(status_code=401, detail="Invalid runner secret")


def python_for_packages(packages: list[str]) -> Path:
    if not packages:
        return Path(sys.executable)
    normalized = sorted(set(package.strip() for package in packages if package.strip()))
    digest = hashlib.sha256("\n".join(normalized).encode()).hexdigest()[:20]
    env_dir = cache_root / "envs" / digest
    python_path = env_dir / "bin" / "python"
    if python_path.exists():
        return python_path

    env_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "venv", str(env_dir)], check=True, capture_output=True, timeout=60)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python_path), *normalized],
        check=True,
        capture_output=True,
        timeout=180,
    )
    return python_path


WRAPPER = r'''
import contextlib
import importlib.util
import io
import json
import sys

source_path, function_name = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("user_source", source_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
payload = json.load(sys.stdin)
captured = io.StringIO()
with contextlib.redirect_stdout(captured):
    result = function(payload)
if not isinstance(result, dict):
    raise TypeError("Data source function must return a dict")
print(json.dumps({"result": result, "logs": captured.getvalue()}, ensure_ascii=False, default=str))
'''


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
        python_path = python_for_packages(request.packages)
        with tempfile.TemporaryDirectory(prefix="investment-source-") as temp_dir:
            temp = Path(temp_dir)
            source_file = temp / "source.py"
            wrapper_file = temp / "wrapper.py"
            source_file.write_text(request.code, encoding="utf-8")
            wrapper_file.write_text(WRAPPER, encoding="utf-8")
            result = subprocess.run(
                [str(python_path), "-I", str(wrapper_file), str(source_file), request.function_name],
                input=json.dumps(request.payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=timeout,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
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
