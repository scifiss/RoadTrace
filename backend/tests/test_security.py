from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import pytest

from app.ingestion.repository import (
    DevelopmentLocalAcquirer,
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
    assert "--filter=blob:none" in captured
    assert any(item.startswith("--depth=") for item in captured)
    assert "--" in captured
    assert captured[-2] == "https://github.com/owner/repository"


def test_local_repository_analysis_is_disabled_by_default(
    settings, synthetic_repository: Path
) -> None:
    with (
        pytest.raises(RepositoryInputError, match="disabled"),
        DevelopmentLocalAcquirer(settings).acquire(str(synthetic_repository)),
    ):
        pass


def test_local_repository_analysis_accepts_only_configured_git_roots(
    settings, synthetic_repository: Path
) -> None:
    enabled = replace(
        settings,
        dev_local_repos=True,
        local_repo_roots=(synthetic_repository.parent,),
    )
    with DevelopmentLocalAcquirer(enabled).acquire(str(synthetic_repository)) as acquired:
        assert acquired.path == synthetic_repository.resolve()
        assert acquired.identity.owner == "local"
        assert acquired.identity.url.startswith("local://")


def test_local_repository_analysis_rejects_escape_and_subdirectory_inputs(
    settings, synthetic_repository: Path, tmp_path: Path
) -> None:
    allowed_root = synthetic_repository
    enabled = replace(
        settings,
        dev_local_repos=True,
        local_repo_roots=(allowed_root,),
    )
    with (
        pytest.raises(RepositoryInputError, match="outside"),
        DevelopmentLocalAcquirer(enabled).acquire(str(tmp_path)),
    ):
        pass
    with (
        pytest.raises(RepositoryInputError, match="top-level"),
        DevelopmentLocalAcquirer(enabled).acquire(str(synthetic_repository / "roadnet")),
    ):
        pass
    escape_link = synthetic_repository / "escape"
    escape_link.symlink_to(tmp_path, target_is_directory=True)
    with (
        pytest.raises(RepositoryInputError, match="outside"),
        DevelopmentLocalAcquirer(enabled).acquire(str(escape_link)),
    ):
        pass
