from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.domain import LensDefinition, LensSet, LensStatus

DEFAULT_LENS_SET = LensSet(
    id="roadtrace-default",
    version="2.0",
    lenses=[
        LensDefinition(
            id="experience-interaction",
            label="Experience & Interaction",
            description="Human-facing journeys, interaction surfaces, and presentation behavior.",
            signals=["interaction", "ui", "render", "view", "form", "search", "display"],
        ),
        LensDefinition(
            id="domain-capability",
            label="Domain Capability",
            description="The software's central domain computations and user-meaningful behavior.",
            signals=["compute", "transform", "analyze", "generate", "manage", "domain"],
        ),
        LensDefinition(
            id="data-state",
            label="Data & State",
            description="Persistence, state transitions, schemas, ingestion, and data movement.",
            signals=["persistence", "state", "read", "write", "schema", "import", "export"],
        ),
        LensDefinition(
            id="knowledge-intelligence",
            label="Knowledge & Intelligence",
            description="Knowledge representation, retrieval, reasoning, models, and inference.",
            signals=["knowledge", "inference", "model", "retrieve", "rank", "learn", "reason"],
        ),
        LensDefinition(
            id="automation-agency",
            label="Automation & Agency",
            description="Triggered, scheduled, autonomous, and orchestrated work.",
            signals=["automation", "orchestrate", "schedule", "trigger", "event", "queue", "agent"],
        ),
        LensDefinition(
            id="interfaces-ecosystem",
            label="Interfaces & Ecosystem",
            description="APIs, protocols, external services, and system integration boundaries.",
            signals=["api", "endpoint", "external", "integration", "protocol", "client", "webhook"],
        ),
        LensDefinition(
            id="trust-governance",
            label="Trust & Governance",
            description="Validation, safety, privacy, access control, and policy enforcement.",
            signals=[
                "validation",
                "security",
                "privacy",
                "permission",
                "sanitize",
                "guard",
                "policy",
            ],
        ),
        LensDefinition(
            id="quality-evaluation",
            label="Quality & Evaluation",
            description="Meaningful verification, evaluation, benchmarking, and failure handling.",
            signals=["test", "evaluation", "benchmark", "assert", "quality", "failure"],
        ),
        LensDefinition(
            id="operations-scale",
            label="Operations & Scale",
            description=(
                "Runtime operation, reliability, deployment automation, and scaling behavior."
            ),
            signals=["operations", "deploy", "monitor", "ci", "pipeline", "container", "scale"],
        ),
        LensDefinition(
            id="distribution-ecosystem",
            label="Distribution & Ecosystem",
            description=(
                "Packaging, installation, delivery channels, plugins, and extension surfaces."
            ),
            signals=[
                "package",
                "distribution",
                "install",
                "release",
                "plugin",
                "extension",
                "publish",
            ],
        ),
    ],
)


def load_lens_set(path: Path | None = None) -> LensSet:
    """Load a bounded, versioned projection without changing inference semantics."""
    if path is None:
        return DEFAULT_LENS_SET.model_copy(deep=True)
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"ROADTRACE_LENS_CONFIG is not a file: {resolved}")
    if resolved.stat().st_size > 100_000:
        raise ValueError("ROADTRACE_LENS_CONFIG must be 100 KB or smaller")
    try:
        return LensSet.model_validate(json.loads(resolved.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Invalid ROADTRACE_LENS_CONFIG: {exc}") from exc


def active_lenses(lens_set: LensSet) -> list[LensDefinition]:
    return [item for item in lens_set.lenses if item.status == LensStatus.ACTIVE]


def lens_label(lens_set: LensSet, lens_id: str) -> str:
    return next((item.label for item in lens_set.lenses if item.id == lens_id), lens_id)
