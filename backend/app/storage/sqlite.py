from __future__ import annotations

import sqlite3
from pathlib import Path

from app.domain import AnalysisResult, AnalysisSummary


class AnalysisStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    repository_owner TEXT NOT NULL,
                    repository_name TEXT NOT NULL,
                    analyzed_at TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )

    def save(self, result: AnalysisResult) -> None:
        payload = result.model_dump_json()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO analyses
                    (id, repository_owner, repository_name, analyzed_at, result_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.id,
                    result.repository.owner,
                    result.repository.name,
                    result.repository.analyzed_at.isoformat(),
                    payload,
                ),
            )

    def get(self, analysis_id: str) -> AnalysisResult | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT result_json FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return AnalysisResult.model_validate_json(row[0]) if row else None

    def list_recent(self, limit: int = 20) -> list[AnalysisSummary]:
        safe_limit = min(max(limit, 1), 100)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT result_json FROM analyses ORDER BY analyzed_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [
            AnalysisSummary(
                id=result.id,
                repository=result.repository,
                capability_count=len(result.capabilities),
            )
            for row in rows
            if (result := AnalysisResult.model_validate_json(row[0]))
        ]
