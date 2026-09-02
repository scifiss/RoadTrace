from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    max_files: int
    max_commits: int
    clone_depth: int
    max_file_bytes: int
    max_source_bytes: int
    max_repository_bytes: int
    max_graph_nodes: int
    max_workflow_depth: int
    clone_timeout_seconds: int
    git_timeout_seconds: int
    openai_api_key: str | None
    openai_model: str | None
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> Settings:
        origins = tuple(
            origin.strip()
            for origin in os.getenv("ROADTRACE_CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        )
        return cls(
            database_path=Path(os.getenv("ROADTRACE_DATABASE_PATH", "roadtrace.sqlite3")),
            max_files=_positive_int("ROADTRACE_MAX_FILES", 3_000),
            max_commits=_positive_int("ROADTRACE_MAX_COMMITS", 500),
            clone_depth=_positive_int("ROADTRACE_CLONE_DEPTH", 5_000),
            max_file_bytes=_positive_int("ROADTRACE_MAX_FILE_BYTES", 1_000_000),
            max_source_bytes=_positive_int("ROADTRACE_MAX_SOURCE_BYTES", 30_000_000),
            max_repository_bytes=_positive_int("ROADTRACE_MAX_REPOSITORY_BYTES", 300_000_000),
            max_graph_nodes=_positive_int("ROADTRACE_MAX_GRAPH_NODES", 180),
            max_workflow_depth=_positive_int("ROADTRACE_MAX_WORKFLOW_DEPTH", 4),
            clone_timeout_seconds=_positive_int("ROADTRACE_CLONE_TIMEOUT_SECONDS", 120),
            git_timeout_seconds=_positive_int("ROADTRACE_GIT_TIMEOUT_SECONDS", 30),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL"),
            cors_origins=origins,
        )
