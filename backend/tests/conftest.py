from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "roadtrace.sqlite3",
        max_files=500,
        max_commits=50,
        clone_depth=50,
        max_file_bytes=500_000,
        max_source_bytes=5_000_000,
        max_repository_bytes=50_000_000,
        max_graph_nodes=100,
        max_workflow_depth=3,
        clone_timeout_seconds=15,
        git_timeout_seconds=10,
        openai_api_key=None,
        openai_model=None,
        cors_origins=("http://localhost:5173",),
    )


def _git(repository: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    return completed.stdout


def _write(repository: Path, relative: str, content: str) -> None:
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def synthetic_repository(tmp_path: Path) -> Iterator[Path]:
    repository = tmp_path / "fixture-repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "fixture@roadtrace.test")
    _git(repository, "config", "user.name", "RoadTrace Fixture")
    started = datetime(2024, 1, 1, 12, 0, 0)

    def commit(index: int, subject: str) -> None:
        timestamp = (started + timedelta(days=index * 30)).isoformat()
        env = os.environ.copy()
        env.update({"GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp})
        _git(repository, "add", ".", env=env)
        _git(repository, "commit", "-m", subject, env=env)

    _write(
        repository,
        "roadnet/cli.py",
        """def main():
    print('Road network ready')

if __name__ == '__main__':
    main()
""",
    )
    commit(0, "initial CLI")

    _write(
        repository,
        "roadnet/engine.py",
        """class RouteEngine:
    def shortest_path(self, points: list[str]) -> list[str]:
        return sorted(points)

def shortest_path(points: list[str]) -> list[str]:
    return RouteEngine().shortest_path(points)
""",
    )
    _write(
        repository,
        "roadnet/cli.py",
        """from roadnet.engine import shortest_path

def main():
    print(shortest_path(['B', 'A']))

if __name__ == '__main__':
    main()
""",
    )
    commit(1, "add route algorithm")

    _write(
        repository,
        "roadnet/storage.py",
        """from pydantic import BaseModel

class RouteModel(BaseModel):
    origin: str
    destination: str

class RouteRepository:
    def save_route(self, route: RouteModel) -> None:
        self.last_route = route
""",
    )
    commit(2, "implement persistence models")

    _write(
        repository,
        "roadnet/api.py",
        """from fastapi import FastAPI
from roadnet.engine import shortest_path
from roadnet.storage import RouteModel

app = FastAPI()

def validate_location(value: str) -> str:
    if not value.strip():
        raise ValueError('location required')
    return value

@app.post('/routes')
def create_route(route: RouteModel):
    return shortest_path([validate_location(route.origin), route.destination])
""",
    )
    commit(3, "create API with security validation")

    _write(
        repository,
        "tests/test_engine.py",
        """from roadnet.engine import shortest_path

def test_shortest_path():
    assert shortest_path(['B', 'A']) == ['A', 'B']
""",
    )
    commit(4, "add algorithm tests")

    _write(
        repository,
        "web/App.tsx",
        """import React from 'react';

export function RouteMap() {
  const handleRoute = () => fetch('/routes');
  return <button onClick={handleRoute}>Trace route</button>;
}
""",
    )
    _write(
        repository,
        ".github/workflows/ci.yml",
        "on: [push]\njobs: {test: {runs-on: ubuntu-latest}}\n",
    )
    _write(
        repository,
        "Dockerfile",
        'FROM python:3.12-slim\nCMD ["python", "-m", "roadnet.cli"]\n',
    )
    _write(
        repository,
        "README.md",
        "# RoadNet\n\nA small route analysis service.\n\nFuture idea: user authentication.\n",
    )
    commit(5, "add UI CI deployment and docs")
    _git(repository, "tag", "v0.1.0")
    yield repository


@pytest.fixture
def product_semantic_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "product-semantic-repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "fixture@roadtrace.test")
    _git(repository, "config", "user.name", "RoadTrace Fixture")
    _write(
        repository,
        "src/applicationStore.js",
        """export function loadApplications() {
  return JSON.parse(localStorage.getItem('tracked-applications') || '[]');
}
export function filterApplications(applications, stageFilter, searchQuery) {
  return applications.filter(
    (role) => role.stage === stageFilter && role.company.includes(searchQuery)
  );
}
export function updateApplicationStage(application, stage) {
  return { ...application, stage };
}
export function saveRoleNotes(application, notes, referral) {
  const records = [{ ...application, notes, referral }];
  localStorage.setItem('tracked-applications', JSON.stringify(records));
}
""",
    )
    _write(
        repository,
        "src/skillFit.js",
        """export function normalizeSkill(skill) { return skill.toLowerCase().trim(); }
export function matchRequirements(candidateSkills, requiredSkills, skillAliases) {
  return requiredSkills.filter((required) => candidateSkills.some(
    (skill) => normalizeSkill(skill) === normalizeSkill(required)
  ));
}
export function calculateWeightedFitScore(candidateSkills, requiredSkills, preferredSkills) {
  const requiredMatches = matchRequirements(candidateSkills, requiredSkills, {});
  const preferredMatches = matchRequirements(candidateSkills, preferredSkills, {});
  return requiredMatches.length * 2 + preferredMatches.length;
}
export function explainRequirementFit(candidateSkills, requirements) {
  return requirements.map((requirement) => ({
    requirement,
    matched: candidateSkills.includes(requirement),
  }));
}
""",
    )
    _write(
        repository,
        "src/App.jsx",
        """import {
  loadApplications,
  filterApplications,
  updateApplicationStage,
  saveRoleNotes,
} from './applicationStore';
import { calculateWeightedFitScore, explainRequirementFit } from './skillFit';
export function ApplicationTracker() {
  const applications = loadApplications();
  const filteredRoles = filterApplications(applications, 'interview', 'research');
  const selectedRole = updateApplicationStage(filteredRoles[0], 'interview');
  saveRoleNotes(selectedRole, 'Prepare system-design examples', 'Employee referral');
  const fitScore = calculateWeightedFitScore(
    ['Python'], selectedRole.requiredSkills, selectedRole.preferredSkills
  );
  const explanation = explainRequirementFit(['Python'], selectedRole.requiredSkills);
  return <main>
    <h1>Application tracking</h1>
    <label>Search applications</label>
    <label>Stage filter</label>
    <section>Role details and notes</section>
    <section>Skill fit score and requirement explanation</section>
  </main>;
}
""",
    )
    _write(
        repository,
        "tests/skillFit.test.js",
        """import { calculateWeightedFitScore, explainRequirementFit } from '../src/skillFit';
describe('weighted candidate skill fit', () => {
  it('scores required skills above preferred skills', () => calculateWeightedFitScore([], [], []));
  it('explains each missing requirement', () => explainRequirementFit([], []));
});
""",
    )
    _write(
        repository,
        "README.md",
        "# Fixture\n\nImplemented application tracking. Future idea: payroll management.\n",
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "implement application tracking and skill fit")
    return repository
