from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import pytest

from app.ingestion.repository import (
    PublicGitHubAcquirer,
    RepositoryInputError,
    validate_github_url,
)


def test_valid_github_url_is_canonicalized() -> None:
    repository = validate_github_url("https://github.com/openai/openai-python.git")
    assert repository.owner == "openai"
    assert repository.name == "openai-python"
    assert repository.url == "https://github.com/openai/openai-python"


@pytest.mark.parametrize(
    "value",
    [
        "git@github.com:owner/repo.git",
        "http://github.com/owner/repo",
        "https://gitlab.com/owner/repo",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner/repo?tab=readme",
        "https://github.com/owner/repo#readme",
        "https://user@github.com/owner/repo",
        "https://github.com:443/owner/repo",
        "https://github.com:notaport/owner/repo",
        "file:///tmp/repo",
        "/tmp/repo",
        "https://github.com/owner/%2e%2e",
        " https://github.com/owner/repo",
    ],
)
def test_malicious_or_non_repository_urls_are_rejected(value: str) -> None:
    with pytest.raises(RepositoryInputError):
        validate_github_url(value)


def test_clone_boundary_uses_bounded_argument_array(settings, tmp_path: Path) -> None:
    acquirer = PublicGitHubAcquirer(settings)
    captured: list[str] = []

    class FakeGit:
        def run(self, args: list[str], **_kwargs) -> str:
            captured.extend(args)
            Path(args[-1]).mkdir()
            return ""

    acquirer.git = FakeGit()  # type: ignore[assignment]
    with ExitStack() as stack:
        acquired = stack.enter_context(acquirer.acquire("https://github.com/owner/repository"))
        assert acquired.path.is_dir()
    assert "--no-recurse-submodules" in captured
    assert any(item.startswith("--depth=") for item in captured)
    assert "--" in captured
    assert captured[-2] == "https://github.com/owner/repository"
