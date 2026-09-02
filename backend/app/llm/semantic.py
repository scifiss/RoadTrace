from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.config import Settings
from app.domain import Capability, CodeEntity, ObservedEvidence


class SemanticCapability(BaseModel):
    capability_id: str
    name: str = Field(min_length=3, max_length=80)
    description: str = Field(min_length=10, max_length=400)
    reasoning_summary: str = Field(min_length=10, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class SemanticBatch(BaseModel):
    capabilities: list[SemanticCapability] = Field(max_length=30)


class SemanticRefiner:
    """Refines deterministic labels; it cannot create or re-categorize capabilities."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openai_api_key and self.settings.openai_model)

    def refine(
        self,
        capabilities: list[Capability],
        entities: list[CodeEntity],
        evidence: list[ObservedEvidence],
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
            payload = _bounded_payload(capabilities, entities, evidence)
            response = client.responses.parse(
                model=self.settings.openai_model,
                store=False,
                input=[
                    {
                        "role": "developer",
                        "content": (
                            "Refine labels for the supplied software capability candidates. "
                            "Source structure is stronger than docs or commit messages. Return "
                            "only supplied candidate IDs, citing only allowed evidence IDs. "
                            "Do not add capabilities, categories, maturity, or facts."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, separators=(",", ":"))},
                ],
                text_format=SemanticBatch,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("No structured semantic result was returned")
            return _apply_validated(capabilities, parsed), [], "openai"
        except Exception as exc:  # Semantic enrichment must never break deterministic analysis.
            return (
                capabilities,
                [f"Semantic refinement failed; used deterministic result ({type(exc).__name__})"],
                "deterministic-fallback",
            )


def _bounded_payload(
    capabilities: list[Capability],
    entities: list[CodeEntity],
    evidence: list[ObservedEvidence],
) -> dict[str, object]:
    entity_by_id = {item.id: item for item in entities}
    evidence_by_id = {item.id: item for item in evidence}
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
        candidates.append(
            {
                "id": capability.id,
                "category": capability.category.value,
                "current_name": capability.name,
                "current_description": capability.description,
                "allowed_evidence_ids": capability.evidence_ids,
                "entities": entity_digest,
                "evidence": evidence_digest,
            }
        )
    return {"candidates": candidates}


def _apply_validated(capabilities: list[Capability], parsed: SemanticBatch) -> list[Capability]:
    original = {item.id: item for item in capabilities}
    updates: dict[str, SemanticCapability] = {}
    for item in parsed.capabilities:
        capability = original.get(item.capability_id)
        if capability is None or not set(item.evidence_ids).issubset(capability.evidence_ids):
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
                }
            )
        )
    return refined
