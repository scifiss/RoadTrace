from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.domain import ChangeType, CommitRecord
from app.ingestion.repository import GitRunner


def classify_change(subject: str, paths: list[str]) -> ChangeType:
    text = subject.lower()
    lowered_paths = [path.lower() for path in paths]
    if any(word in text for word in ("remove", "delete", "drop", "deprecat")):
        return ChangeType.REMOVAL
    if any(word in text for word in ("fix", "bug", "patch", "hotfix")):
        return ChangeType.BUG_FIX
    if any(word in text for word in ("refactor", "cleanup", "rename", "reorgan")):
        return ChangeType.REFACTOR
    if "migrat" in text:
        return ChangeType.MIGRATION
    if any("test" in path for path in lowered_paths) or any(
        word in text for word in ("test", "coverage", "benchmark", "eval")
    ):
        return ChangeType.TEST_MATURATION
    if lowered_paths and all(
        path.endswith((".md", ".rst", ".txt")) or "/docs/" in f"/{path}" for path in lowered_paths
    ):
        return ChangeType.DOCUMENTATION
    if any(
        marker in path
        for path in lowered_paths
        for marker in (".github/", "docker", "deploy", "terraform", "workflow")
    ):
        return ChangeType.OPERATIONS
    if any(word in text for word in ("add", "create", "initial", "implement", "introduce")):
        return ChangeType.NEW_CAPABILITY
    return ChangeType.ENHANCEMENT


class GitHistoryAnalyzer:
    def __init__(self, runner: GitRunner, max_commits: int) -> None:
        self.runner = runner
        self.max_commits = max_commits

    def analyze(self, repository: Path) -> tuple[list[CommitRecord], str | None, list[str]]:
        hashes = [
            item
            for item in self.runner.run(
                ["rev-list", "--reverse", "HEAD"], cwd=repository
            ).splitlines()
            if item
        ]
        selected_hashes = _sample_commit_hashes(hashes, self.max_commits)
        output = self.runner.run(
            [
                "log",
                "--no-walk=unsorted",
                "--date=iso-strict",
                "--no-renames",
                "--name-only",
                "--format=@@ROADTRACE@@%H%x1f%aI%x1f%an%x1f%s",
                *selected_hashes,
            ],
            cwd=repository,
        )
        commits = self._parse(output)
        tags = self._tags(repository)
        for commit in commits:
            commit.tags = tags.get(commit.hash, [])
        commits.sort(key=lambda commit: commit.timestamp)
        warnings: list[str] = []
        if len(hashes) > len(selected_hashes):
            warnings.append(
                f"History overview samples {len(selected_hashes)} commits across "
                f"{len(hashes)} reachable commits"
            )
        shallow = self.runner.run(["rev-parse", "--is-shallow-repository"], cwd=repository).strip()
        if shallow == "true":
            warnings.append(
                f"Repository history is bounded to the newest {len(hashes)} commits by clone depth"
            )
        branch_output = self.runner.run(
            ["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=repository
        ).strip()
        return commits, branch_output or None, warnings

    def _tags(self, repository: Path) -> dict[str, list[str]]:
        output = self.runner.run(
            [
                "for-each-ref",
                "--merged=HEAD",
                "--format=%(refname:short)%09%(*objectname)%09%(objectname)",
                "refs/tags",
            ],
            cwd=repository,
        )
        result: dict[str, list[str]] = {}
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            name, peeled, direct = parts
            commit_hash = peeled or direct
            result.setdefault(commit_hash, []).append(name)
        return result

    @staticmethod
    def _parse(output: str) -> list[CommitRecord]:
        commits: list[CommitRecord] = []
        current: dict[str, object] | None = None
        for line in output.splitlines():
            if line.startswith("@@ROADTRACE@@"):
                if current is not None:
                    commits.append(_commit_from_parts(current))
                parts = line.removeprefix("@@ROADTRACE@@").split("\x1f", 3)
                if len(parts) != 4:
                    current = None
                    continue
                current = {
                    "hash": parts[0],
                    "timestamp": parts[1],
                    "author": parts[2],
                    "subject": parts[3],
                    "paths": [],
                    "additions": 0,
                    "deletions": 0,
                }
                continue
            if current is None or not line:
                continue
            paths = current["paths"]
            assert isinstance(paths, list)
            if "\t" not in line:
                paths.append(line)
                continue
            additions, deletions, path = line.split("\t", 2)
            paths.append(path)
            if additions.isdigit():
                current["additions"] = int(current["additions"]) + int(additions)
            if deletions.isdigit():
                current["deletions"] = int(current["deletions"]) + int(deletions)
        if current is not None:
            commits.append(_commit_from_parts(current))
        return commits


def _sample_commit_hashes(hashes: list[str], limit: int) -> list[str]:
    if len(hashes) <= limit:
        return hashes
    if limit == 1:
        return [hashes[0]]

    recent_count = max(1, limit // 2)
    historical_count = limit - recent_count
    older = hashes[:-recent_count]
    recent = hashes[-recent_count:]
    if historical_count == 1:
        historical = [older[0]]
    else:
        last_index = len(older) - 1
        historical = [
            older[round(index * last_index / (historical_count - 1))]
            for index in range(historical_count)
        ]
    return list(dict.fromkeys([*historical, *recent]))


def _commit_from_parts(parts: dict[str, object]) -> CommitRecord:
    changed_paths = [str(path) for path in parts["paths"]]  # type: ignore[union-attr]
    return CommitRecord(
        hash=str(parts["hash"]),
        short_hash=str(parts["hash"])[:8],
        timestamp=datetime.fromisoformat(str(parts["timestamp"])),
        author=str(parts["author"]),
        subject=str(parts["subject"]),
        changed_paths=changed_paths,
        additions=int(parts["additions"]),
        deletions=int(parts["deletions"]),
        change_type=classify_change(str(parts["subject"]), changed_paths),
    )
