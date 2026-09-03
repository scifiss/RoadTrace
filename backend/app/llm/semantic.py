from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.config import Settings
from app.domain import (
    BehaviorSummary,
    Capability,
    CodeEntity,
    LensSet,
    Observation,
    ObservedEvidence,
)
from app.taxonomy import DEFAULT_LENS_SET, active_lenses, lens_label


class SemanticCapability(BaseModel):
    capability_id: str
    name: str = Field(min_length=3, max_length=80)
    description: str = Field(min_length=10, max_length=400)
    reasoning_summary: str = Field(min_length=10, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    behavior_ids: list[str] = Field(min_length=1, max_length=12)
    primary_lens: str = Field(min_length=2, max_length=80)
    secondary_lenses: list[str] = Field(default_factory=list, max_length=4)
    parent_capability_id: str | None = None
    merge_into_capability_id: str | None = None


class SemanticBatch(BaseModel):
    capabilities: list[SemanticCapability] = Field(max_length=30)


class SemanticRefiner:
    """Refines and merges deterministic behavior-backed candidates within evidence bounds."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openai_api_key and self.settings.openai_model)

    def refine(
        self,
        capabilities: list[Capability],
        behaviors: list[BehaviorSummary],
        observations: list[Observation],
        entities: list[CodeEntity],
        evidence: list[ObservedEvidence],
        lens_set: LensSet,
    ) -> tuple[list[Capability], list[str], str]:
        if not self.enabled:
            warning = []
            if self.settings.openai_api_key and not self.settings.openai_model:
                warning.append(
                    "OPENAI_API_KEY is set but OPENAI_MODEL is missing; used deterministic mode"
                )
            return capabilities, warning, "deterministic"

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.settings.openai_api_key)
            payload = _bounded_payload(
                capabilities, behaviors, observations, entities, evidence, lens_set
            )
            response = client.responses.parse(
                model=self.settings.openai_model,
                store=False,
                input=[
                    {
                        "role": "developer",
                        "content": (
                            "Synthesize product-semantic software capabilities from the supplied "
                            "behavior-backed candidates. Infer open-world domain concepts; "
                            "do not use a predeclared product vocabulary. Source implementation "
                            "is stronger than "
                            "documentation claims. You may rename, project into one supplied lens, "
                            "establish hierarchy, or merge supplied candidates, but cannot add "
                            "IDs, "
                            "observations, behaviors, evidence, maturity, or facts. Names must "
                            "describe roadmap-level behaviors, never "
                            "generic artifacts such as API Surface, JSON Engine, UI, parser, file, "
                            "or helper. Cite only the candidate's allowed evidence and "
                            "behavior IDs."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, separators=(",", ":"))},
                ],
                text_format=SemanticBatch,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("No structured semantic result was returned")
            return _apply_validated(capabilities, parsed, lens_set), [], "openai"
        except Exception as exc:  # Semantic enrichment must never break deterministic analysis.
            return (
                capabilities,
                [f"Semantic refinement failed; used deterministic result ({type(exc).__name__})"],
                "deterministic-fallback",
            )


def _bounded_payload(
    capabilities: list[Capability],
    behaviors: list[BehaviorSummary],
    observations: list[Observation],
    entities: list[CodeEntity],
    evidence: list[ObservedEvidence],
    lens_set: LensSet,
) -> dict[str, object]:
    entity_by_id = {item.id: item for item in entities}
    evidence_by_id = {item.id: item for item in evidence}
    behavior_by_id = {item.id: item for item in behaviors}
    observation_by_id = {item.id: item for item in observations}
    candidates: list[dict[str, object]] = []
    for capability in capabilities[:30]:
        entity_digest = [
            {
                "id": item.id,
                "type": item.type.value,
                "name": item.qualified_name,
                "path": item.file_path,
            }
            for entity_id in capability.entity_ids[:20]
            if (item := entity_by_id.get(entity_id)) is not None
        ]
        evidence_digest = [
            {
                "id": item.id,
                "kind": item.kind.value,
                "label": item.label,
                "path": item.file_path,
            }
            for evidence_id in capability.evidence_ids[:30]
            if (item := evidence_by_id.get(evidence_id)) is not None
        ]
        behavior_digest = [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "semantic_terms": item.semantic_terms,
                "inputs": item.observable_inputs[:8],
                "outputs": item.observable_outputs[:8],
                "ui_surfaces": item.ui_surfaces[:8],
                "api_paths": item.api_paths[:8],
                "tests": item.tests[:8],
                "mechanism_types": item.mechanism_types,
                "observation_ids": item.observation_ids,
                "allowed_evidence_ids": item.evidence_ids,
            }
            for behavior_id in capability.behavior_ids[:12]
            if (item := behavior_by_id.get(behavior_id)) is not None
        ]
        candidates.append(
            {
                "id": capability.id,
                "primary_lens": capability.primary_lens,
                "current_name": capability.name,
                "current_description": capability.description,
                "allowed_evidence_ids": capability.evidence_ids,
                "allowed_behavior_ids": capability.behavior_ids,
                "allowed_observation_ids": capability.observation_ids,
                "behaviors": behavior_digest,
                "entities": entity_digest,
                "evidence": evidence_digest,
                "observations": [
                    {
                        "id": item.id,
                        "kind": item.kind.value,
                        "summary": item.summary,
                        "evidence_ids": item.evidence_ids,
                        "structural": item.structural,
                    }
                    for observation_id in capability.observation_ids[:35]
                    if (item := observation_by_id.get(observation_id)) is not None
                ],
            }
        )
    return {
        "lens_set": {
            "id": lens_set.id,
            "version": lens_set.version,
            "lenses": [
                {"id": item.id, "label": item.label, "description": item.description}
                for item in active_lenses(lens_set)
            ],
        },
        "candidates": candidates,
    }


def _apply_validated(
    capabilities: list[Capability],
    parsed: SemanticBatch,
    lens_set: LensSet | None = None,
) -> list[Capability]:
    selected_lenses = lens_set or DEFAULT_LENS_SET
    valid_lenses = {item.id for item in active_lenses(selected_lenses)}
    original = {item.id: item for item in capabilities}
    updates: dict[str, SemanticCapability] = {}
    for item in parsed.capabilities:
        capability = original.get(item.capability_id)
        if (
            capability is None
            or not set(item.evidence_ids).issubset(capability.evidence_ids)
            or not set(item.behavior_ids).issubset(capability.behavior_ids)
            or item.primary_lens not in valid_lenses
            or not set(item.secondary_lenses).issubset(valid_lenses)
        ):
            continue
        updates[item.capability_id] = item
    refined: list[Capability] = []
    for capability in capabilities:
        update = updates.get(capability.id)
        if update is None:
            refined.append(capability)
            continue
        refined.append(
            capability.model_copy(
                update={
                    "name": update.name,
                    "description": update.description,
                    "reasoning_summary": update.reasoning_summary,
                    "primary_lens": update.primary_lens,
                    "secondary_lenses": [
                        item for item in update.secondary_lenses if item != update.primary_lens
                    ],
                    "category": lens_label(selected_lenses, update.primary_lens),
                    "secondary_categories": [
                        lens_label(selected_lenses, item)
                        for item in update.secondary_lenses
                        if item != update.primary_lens
                    ],
                    "parent_id": update.parent_capability_id,
                }
            )
        )
    refined_by_id = {item.id: item for item in refined}
    removed: set[str] = set()
    for source_id, update in updates.items():
        target_id = update.merge_into_capability_id
        if not target_id or target_id == source_id:
            continue
        source = refined_by_id.get(source_id)
        target = refined_by_id.get(target_id)
        if source is None or target is None or source.primary_lens != target.primary_lens:
            continue
        target.behavior_ids = _unique([*target.behavior_ids, *source.behavior_ids])
        target.entity_ids = _unique([*target.entity_ids, *source.entity_ids])[:80]
        target.evidence_ids = _unique([*target.evidence_ids, *source.evidence_ids])[:140]
        target.commit_hashes = _unique([*target.commit_hashes, *source.commit_hashes])
        target.aliases = _unique([*target.aliases, source.name, *source.aliases])
        target.secondary_lenses = _unique([*target.secondary_lenses, *source.secondary_lenses])
        target.secondary_categories = _unique(
            [*target.secondary_categories, *source.secondary_categories]
        )
        target.observation_ids = _unique([*target.observation_ids, *source.observation_ids])[:180]
        target.confidence = max(target.confidence, source.confidence)
        removed.add(source_id)
        for candidate in refined:
            if candidate.parent_id == source_id:
                candidate.parent_id = target_id
    return _merge_duplicate_names([item for item in refined if item.id not in removed])


def _merge_duplicate_names(capabilities: list[Capability]) -> list[Capability]:
    result: list[Capability] = []
    by_key: dict[tuple[str | None, str], Capability] = {}
    for item in capabilities:
        key = (item.primary_lens, _normalized_name(item.name))
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = item
            result.append(item)
            continue
        existing.behavior_ids = _unique([*existing.behavior_ids, *item.behavior_ids])
        existing.entity_ids = _unique([*existing.entity_ids, *item.entity_ids])[:80]
        existing.evidence_ids = _unique([*existing.evidence_ids, *item.evidence_ids])[:140]
        existing.aliases = _unique([*existing.aliases, item.name, *item.aliases])
        existing.confidence = max(existing.confidence, item.confidence)
    return result


def _normalized_name(value: str) -> str:
    characters = "".join(char if char.isalnum() else " " for char in value.lower())
    tokens = characters.split()
    return " ".join(
        token[:-1] if len(token) > 4 and token.endswith("s") and not token.endswith("ss") else token
        for token in tokens
    )


def _unique[T](items: list[T]) -> list[T]:
    return list(dict.fromkeys(items))
