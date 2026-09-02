from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.config import Settings


class RepositoryInputError(ValueError):
    pass


class RepositoryAcquisitionError(RuntimeError):
    pass


_SEGMENT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9])?$")


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    owner: str
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class AcquiredRepository:
    identity: GitHubRepository
    path: Path


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: str
    absolute_path: Path
    language: str
    size: int
    content: str


def validate_github_url(value: str) -> GitHubRepository:
    if value != value.strip() or len(value) > 300 or "%" in value or "\\" in value:
        raise RepositoryInputError("Enter an exact public GitHub repository URL")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RepositoryInputError("The GitHub URL contains an invalid port") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RepositoryInputError("Only https://github.com/{owner}/{repo} URLs are accepted")
    decoded_path = unquote(parsed.path)
    parts = decoded_path.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise RepositoryInputError("The URL must identify one GitHub owner and repository")
    owner, name = parts
    if name.endswith(".git"):
        name = name[:-4]
    if (
        not _SEGMENT.fullmatch(owner)
        or not _SEGMENT.fullmatch(name)
        or owner in {".", ".."}
        or name in {".", ".."}
    ):
        raise RepositoryInputError("The GitHub owner or repository name is invalid")
    return GitHubRepository(owner=owner, name=name, url=f"https://github.com/{owner}/{name}")


class GitRunner:
    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, args: list[str], cwd: Path | None = None, timeout: int | None = None) -> str:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "",
                "GIT_LFS_SKIP_SMUDGE": "1",
            }
        )
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                errors="replace",
                shell=False,
                check=False,
                timeout=timeout or self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepositoryAcquisitionError(f"Git operation failed safely: {exc}") from exc
        if completed.returncode != 0:
            message = completed.stderr.strip().splitlines()[-1:] or ["unknown Git error"]
            raise RepositoryAcquisitionError(message[0][:300])
        return completed.stdout


class PublicGitHubAcquirer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.git = GitRunner(settings.git_timeout_seconds)

    @contextmanager
    def acquire(self, repository_url: str) -> Iterator[AcquiredRepository]:
        identity = validate_github_url(repository_url)
        with tempfile.TemporaryDirectory(prefix="roadtrace-") as temp:
            temp_path = Path(temp)
            destination = temp_path / "repository"
            hooks = temp_path / "disabled-hooks"
            template = temp_path / "empty-template"
            hooks.mkdir()
            template.mkdir()
            args = [
                "-c",
                f"core.hooksPath={hooks}",
                "-c",
                "protocol.file.allow=never",
                "clone",
                "--quiet",
                "--single-branch",
                "--no-recurse-submodules",
                f"--depth={self.settings.clone_depth}",
                "--filter=blob:none",
                f"--template={template}",
                "--",
                identity.url,
                str(destination),
            ]
            self.git.run(args, timeout=self.settings.clone_timeout_seconds)
            repository_bytes = _directory_size(destination)
            if repository_bytes > self.settings.max_repository_bytes:
                raise RepositoryAcquisitionError(
                    "Repository exceeds the configured clone size limit "
                    f"({self.settings.max_repository_bytes} bytes)"
                )
            yield AcquiredRepository(identity=identity, path=destination)


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    ".next",
    ".nuxt",
    ".cache",
    "target",
    "__pycache__",
}

IGNORED_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "Cargo.lock",
}

LANGUAGES = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
}

TEXT_EXTENSIONS = {
    ".md",
    ".rst",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".sql",
    ".env.example",
}

SPECIAL_TEXT_FILES = {
    "Dockerfile",
    "Makefile",
    "Procfile",
    "README",
    "LICENSE",
    ".gitignore",
    ".dockerignore",
}


def _file_language(path: Path) -> str:
    if path.suffix.lower() in LANGUAGES:
        return LANGUAGES[path.suffix.lower()]
    if path.suffix.lower() in {".md", ".rst", ".txt"} or path.name.startswith("README"):
        return "Documentation"
    return "Configuration"


def collect_source_files(root: Path, settings: Settings) -> tuple[list[SourceFile], list[str]]:
    root = root.resolve()
    files: list[SourceFile] = []
    warnings: list[str] = []
    total_bytes = 0
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name not in IGNORED_DIRECTORIES and not (Path(current) / name).is_symlink()
        )
        for name in sorted(names):
            path = Path(current) / name
            suffix = path.suffix.lower()
            eligible = (
                suffix in LANGUAGES or suffix in TEXT_EXTENSIONS or name in SPECIAL_TEXT_FILES
            )
            if not eligible or name in IGNORED_NAMES or path.is_symlink() or not path.is_file():
                continue
            try:
                relative = path.resolve().relative_to(root).as_posix()
                size = path.stat().st_size
            except (OSError, ValueError):
                continue
            if size > settings.max_file_bytes:
                warnings.append(f"Skipped oversized file: {relative}")
                continue
            if len(files) >= settings.max_files:
                warnings.append(f"File limit reached ({settings.max_files}); analysis is truncated")
                return files, warnings
            if total_bytes + size > settings.max_source_bytes:
                warnings.append(
                    f"Source byte limit reached ({settings.max_source_bytes}); "
                    "analysis is truncated"
                )
                return files, warnings
            try:
                raw = path.read_bytes()
            except OSError:
                warnings.append(f"Could not read file: {relative}")
                continue
            if b"\x00" in raw[:8192]:
                continue
            content = raw.decode("utf-8", errors="replace")
            files.append(
                SourceFile(
                    path=relative,
                    absolute_path=path,
                    language=_file_language(path),
                    size=size,
                    content=content,
                )
            )
            total_bytes += size
    return files, warnings


def ensure_git_available() -> None:
    if shutil.which("git") is None:
        raise RepositoryAcquisitionError("Git is required but was not found")


def _directory_size(root: Path) -> int:
    total = 0
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if not (Path(current) / name).is_symlink()]
        for name in files:
            path = Path(current) / name
            if path.is_symlink():
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total
