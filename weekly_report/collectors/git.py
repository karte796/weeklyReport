"""Collect commits from every git repository under the configured roots (read-only)."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Optional

from weekly_report.periods import Period

SKIP_DIRS = {"node_modules", "vendor", "Pods", ".venv", "venv", "build", "dist", "DerivedData"}


@dataclass
class Commit:
    date: str
    short_hash: str
    subject: str


@dataclass
class RepoCommits:
    name: str
    path: Path
    commits: list[Commit] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable identity used by the GUI selection."""
        return str(self.path)


def run_git(repo: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def find_repos(root: Path, max_depth: int) -> list[Path]:
    """Find directories containing .git (dir or worktree file), pruning dependency folders."""
    repos: list[Path] = []
    if not root.is_dir():
        return repos

    def walk(directory: Path, depth: int) -> None:
        if (directory / ".git").exists():
            repos.append(directory)
        if depth >= max_depth:
            return
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_dir() and not child.is_symlink() and child.name not in SKIP_DIRS \
                    and not child.name.startswith("."):
                walk(child, depth + 1)

    walk(root, 0)
    return repos


def canonical_repo(repo: Path) -> Path:
    """Map a worktree to its main repository so commits are counted once."""
    out = run_git(repo, ["rev-parse", "--git-common-dir"]).strip()
    if not out:
        return repo.resolve()
    common = Path(out)
    common = (repo / common).resolve() if not common.is_absolute() else common.resolve()
    return common.parent if common.name == ".git" else common


def repo_author(repo: Path) -> str:
    """The repo's effective user.email (honours local config and includeIf)."""
    return run_git(repo, ["config", "user.email"]).strip()


@lru_cache(maxsize=1)
def _filter_supported() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10).stdout
    except (subprocess.SubprocessError, OSError):
        return False
    match = re.search(r"(\d+)\.(\d+)", out)
    return bool(match) and (int(match.group(1)), int(match.group(2))) >= (2, 37)


def collect_repo(repo: Path, authors: list[str], period: Period,
                 keywords: Optional[list[str]] = None) -> list[Commit]:
    until = period.end + timedelta(days=1)
    since = f"{period.start.isoformat()} 00:00:00"
    common = [
        "log", "--all", "--no-merges",
        f"--until={until.isoformat()} 00:00:00",
        "--pretty=format:%cd%x09%h%x09%s",
        "--date=format-local:%Y-%m-%d",
        *[f"--author={author}" for author in authors],
    ]
    # --since stops walking at the first older commit, which hides commits after
    # rebases/cherry-picks; --since-as-filter (git >= 2.37) checks every commit.
    output = run_git(repo, [*common, f"--since-as-filter={since}"]) if _filter_supported() else ""
    if not output:
        output = run_git(repo, [*common, f"--since={since}"])
    lowered = [k.lower() for k in keywords or []]
    seen: set[str] = set()
    commits: list[Commit] = []
    for line in output.splitlines():
        parts = line.strip().split("\t", 2)
        if len(parts) < 3 or parts[1] in seen:
            continue
        day, short_hash, subject = parts
        if lowered and not any(k in subject.lower() for k in lowered):
            continue
        seen.add(short_hash)
        commits.append(Commit(day, short_hash, subject.strip()))
    commits.sort(key=lambda c: c.date)
    return commits


def collect_git(roots: Iterable[Path], period: Period, authors: Optional[list[str]] = None,
                max_depth: int = 4, exclude: Optional[list[str]] = None,
                keywords: Optional[list[str]] = None,
                progress: Optional[Callable[[dict], None]] = None,
                cancel: Optional[Callable[[], bool]] = None) -> tuple[list[RepoCommits], int, bool]:
    """Return (repos with commits, number of repos scanned, cancelled).

    `cancel` is polled between steps; a cancelled run stops early and returns
    the repos collected so far. `progress` receives {phase, current, ...} events:
    "discover" while locating repositories, "collect" per repository.
    """
    canonical: dict[Path, Path] = {}
    cancelled = False
    for root in roots:
        if cancel and cancel():
            cancelled = True
            break
        for repo in find_repos(root, max_depth):
            main = canonical_repo(repo)
            if any(pattern and pattern in str(main) for pattern in exclude or []):
                continue
            canonical.setdefault(main, main)
            if progress:
                progress({"phase": "discover", "current": str(main), "scanned": len(canonical)})

    results: list[RepoCommits] = []
    ordered = sorted(canonical)
    for index, repo in enumerate(ordered):
        if cancel and cancel():
            cancelled = True
            break
        if progress:
            progress({"phase": "collect", "scanned": index, "total": len(ordered),
                      "current": repo.name})
        repo_authors = list(authors or [])
        if not repo_authors:
            email = repo_author(repo)
            if not email:
                continue  # unknown identity: skip rather than collect everyone's commits
            repo_authors = [email]
        commits = collect_repo(repo, repo_authors, period, keywords)
        if commits:
            results.append(RepoCommits(repo.name, repo, commits))
    results.sort(key=lambda r: -len(r.commits))
    return results, len(canonical), cancelled
