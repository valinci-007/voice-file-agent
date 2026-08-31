"""Hands — thin, testable wrappers over macOS primitives.

Pure logic (query building, ranking, formatting) is split from subprocess
calls so unit tests never need Spotlight, Finder, or a Mac at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

HOME = Path.home()

# Folders a person usually means when they say "my files" — ranked up.
PREFERRED_DIRS = [
    str(HOME / d) for d in ("Desktop", "Documents", "Downloads", "Pictures", "Movies", "Music")
]

# Path fragments that are almost never what the user wants — ranked down hard.
NOISE_FRAGMENTS = [
    "/Library/", "/.git/", "/node_modules/", "/.Trash/", "/site-packages/",
    ".app/", "/System/", "/private/", "/.venv/", "/venv/", "/__pycache__/",
    "/.cache/", "/Caches/",
]


def _sh(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n}B"


def score(path: str) -> int:
    """Relevance prior for a result path (before recency tie-break)."""
    s = 0
    if any(path.startswith(d) for d in PREFERRED_DIRS):
        s += 50
    elif path.startswith(str(HOME)):
        s += 10
    if any(frag in path for frag in NOISE_FRAGMENTS):
        s -= 100
    s -= path.count("/")  # shallow paths beat deeply buried ones
    return s


def build_search_command(
    query: str,
    search_by: str,
    scope_dir: str,
    modified_within_days: int = 0,
    file_extension: str = "",
) -> list[str] | None:
    """Build the mdfind argv for a search, or None if there are no criteria."""
    query = query.replace('"', "").replace("\\", "").strip()
    ext = file_extension.lower().lstrip(".") if file_extension else ""

    clauses = []
    if query:
        attr = "kMDItemDisplayName" if search_by == "name" else "kMDItemTextContent"
        clauses.append(f'{attr} == "*{query}*"c')
    if ext:
        clauses.append(f'kMDItemFSName == "*.{ext}"c')
    if modified_within_days > 0:
        clauses.append(f"kMDItemFSContentChangeDate >= $time.today(-{int(modified_within_days)})")
    if not clauses:
        return None

    if query and not ext and modified_within_days <= 0:
        # single-term searches: mdfind's native modes match Spotlight's own behavior best
        return ["mdfind", "-onlyin", scope_dir] + (
            ["-name", query] if search_by == "name" else [query]
        )
    return ["mdfind", "-onlyin", scope_dir, " && ".join(clauses)]


def rank(paths: list[str], mtime=None) -> list[str]:
    """Order results by relevance prior, then recency. mtime is injectable for tests."""
    if mtime is None:
        def mtime(p: str) -> float:
            try:
                return os.stat(p).st_mtime
            except OSError:
                return 0.0
    return sorted(paths, key=lambda p: (-score(p), -mtime(p)))


def search_files(
    query: str,
    search_by: str = "name",
    scope: str = "~",
    modified_within_days: int = 0,
    file_extension: str = "",
    limit: int = 12,
) -> str:
    scope_dir = os.path.expanduser(scope or "~")
    cmd = build_search_command(query, search_by, scope_dir, modified_within_days, file_extension)
    if cmd is None:
        return json.dumps({"error": "give at least a query, file_extension, or modified_within_days"})

    try:
        out = _sh(cmd).stdout
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Spotlight search timed out"})

    paths = [p for p in out.splitlines() if p.strip()]
    if file_extension:
        ext = "." + file_extension.lower().lstrip(".")
        paths = [p for p in paths if p.lower().endswith(ext)]

    results = []
    for p in rank(paths)[: max(1, min(limit, 30))]:
        try:
            st = os.stat(p)
            is_dir = os.path.isdir(p)
            results.append({
                "path": p,
                "name": os.path.basename(p),
                "kind": "folder" if is_dir else (os.path.splitext(p)[1].lstrip(".").lower() or "file"),
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                "size": "" if is_dir else human_size(st.st_size),
            })
        except OSError:
            continue

    return json.dumps(
        {"total_found": len(paths), "showing": len(results), "results": results},
        ensure_ascii=False,
    )


def list_installed_apps() -> str:
    apps: set[str] = set()
    roots = [
        Path("/Applications"), Path("/System/Applications"),
        Path("/System/Applications/Utilities"), HOME / "Applications",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.suffix == ".app":
                apps.add(entry.stem)
            elif entry.is_dir() and not entry.name.startswith("."):
                for sub in entry.glob("*.app"):
                    apps.add(sub.stem)
    return json.dumps({"count": len(apps), "apps": sorted(apps)}, ensure_ascii=False)


def open_path(path: str, app: str = "", reveal: bool = False) -> str:
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"Error: no such path: {path}"
    if reveal:
        cmd = ["open", "-R", path]
    elif app:
        cmd = ["open", "-a", app, path]
    else:
        cmd = ["open", path]
    try:
        proc = _sh(cmd, timeout=30)
    except subprocess.TimeoutExpired:
        return "Error: open command timed out"
    if proc.returncode != 0:
        return f"Error: {proc.stderr.strip() or 'open failed'}"
    if reveal:
        return f"Revealed {path} in Finder"
    return f"Opened {path}" + (f" with {app}" if app else " with its default app")
