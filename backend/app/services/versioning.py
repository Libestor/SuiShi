from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.config import get_settings


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, timeout=15
    )
    return result.stdout.strip()


def save_data_source_version(source_id: str, name: str, code: str, packages: list[str]) -> str:
    repo = Path(get_settings().data_source_repo)
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        _run_git(repo, "init", "-b", "main")
        _run_git(repo, "config", "user.name", "Investment Overview")
        _run_git(repo, "config", "user.email", "investment-overview@localhost")

    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", source_id)
    source_dir = repo / safe_id
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "source.py").write_text(code, encoding="utf-8")
    (source_dir / "packages.txt").write_text("\n".join(packages) + "\n", encoding="utf-8")
    _run_git(repo, "add", str(source_dir.relative_to(repo)))
    _run_git(repo, "commit", "--allow-empty", "-m", f"data-source: {name}")
    return _run_git(repo, "rev-parse", "HEAD")
