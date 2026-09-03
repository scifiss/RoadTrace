from app.domain import Capability, MaturitySignals, MaturityState
from app.llm.semantic import SemanticBatch, SemanticCapability, _apply_validated


def capability(
    capability_id: str,
    name: str,
    evidence_id: str,
    behavior_id: str,
) -> Capability:
    return Capability(
        id=capability_id,
        name=name,
        description=f"Implemented behavior for {name}.",
        primary_lens="experience-interaction",
        category="Experience & Interaction",
        behavior_ids=[behavior_id],
        evidence_ids=[evidence_id],
        maturity=MaturityState.FUNCTIONAL,
        maturity_signals=MaturitySignals(implementation=True),
        confidence=0.8,
        reasoning_summary=f"Observed implementation evidence for {name}.",
    )


def semantic_update(
    capability_id: str,
    name: str,
    evidence_id: str,
    behavior_id: str,
    *,
    merge_into: str | None = None,
    primary_lens: str = "experience-interaction",
) -> SemanticCapability:
    return SemanticCapability(
        capability_id=capability_id,
        name=name,
        description=f"Refined implemented behavior for {name}.",
        reasoning_summary=f"Observed code supports the refined {name} behavior.",
        evidence_ids=[evidence_id],
        behavior_ids=[behavior_id],
        primary_lens=primary_lens,
        merge_into_capability_id=merge_into,
    )


def test_semantic_refinement_rejects_unknown_evidence_and_behavior_ids() -> None:
    original = capability("cap-a", "Inventory Monitor", "evidence-a", "behavior-a")
    batch = SemanticBatch(
        capabilities=[
            semantic_update(
                "cap-a",
                "Invented Payroll Management",
                "invented-evidence",
                "behavior-a",
            )
        ]
    )
    assert _apply_validated([original], batch) == [original]


def test_semantic_refinement_rejects_unknown_lenses() -> None:
    original = capability("cap-a", "Inventory Monitor", "evidence-a", "behavior-a")
    batch = SemanticBatch(
        capabilities=[
            semantic_update(
                "cap-a",
                "Inventory Oversight",
                "evidence-a",
                "behavior-a",
                primary_lens="invented-lens",
            )
        ]
    )
    assert _apply_validated([original], batch) == [original]


def test_semantic_refinement_can_merge_only_existing_grounded_candidates() -> None:
    target = capability("cap-a", "Inventory Monitoring", "evidence-a", "behavior-a")
    source = capability("cap-b", "Stock Tracking", "evidence-b", "behavior-b")
    batch = SemanticBatch(
        capabilities=[
            semantic_update(
                "cap-b",
                "Inventory Management",
                "evidence-b",
                "behavior-b",
                merge_into="cap-a",
            )
        ]
    )
    refined = _apply_validated([target, source], batch)
    assert len(refined) == 1
    assert refined[0].behavior_ids == ["behavior-a", "behavior-b"]
    assert refined[0].evidence_ids == ["evidence-a", "evidence-b"]
    assert "Inventory Management" in refined[0].aliases
