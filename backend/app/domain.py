from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CanonicalCategory(StrEnum):
    PRODUCT_UX = "Product & UX"
    CORE = "Core Capability"
    DATA = "Data"
    PLATFORM = "Platform & Integration"
    RELIABILITY = "Reliability & Safety"
    QUALITY = "Quality & Evaluation"
    OPERATIONS = "Operations"
    DEVELOPER = "Developer & Documentation"


class EvidenceKind(StrEnum):
    SOURCE = "SOURCE"
    TEST = "TEST"
    API = "API"
    SCHEMA = "SCHEMA"
    UI = "UI"
    CONFIGURATION = "CONFIGURATION"
    DEPENDENCY = "DEPENDENCY"
    COMMIT = "COMMIT"
    DOCUMENTATION = "DOCUMENTATION"


class EntityType(StrEnum):
    FILE = "FILE"
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    API_ENDPOINT = "API_ENDPOINT"
    UI_COMPONENT = "UI_COMPONENT"
    SCHEMA = "SCHEMA"
    TEST = "TEST"
    CONFIGURATION = "CONFIGURATION"
    EXTERNAL_MODULE = "EXTERNAL_MODULE"


class RelationshipType(StrEnum):
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    INSTANTIATES = "INSTANTIATES"
    READS = "READS"
    WRITES = "WRITES"
    EXPOSES = "EXPOSES"
    TESTS = "TESTS"
    RENDERS = "RENDERS"
    DEPENDS_ON = "DEPENDS_ON"


class MaturityState(StrEnum):
    DISCOVERED = "DISCOVERED"
    SCAFFOLDED = "SCAFFOLDED"
    FUNCTIONAL = "FUNCTIONAL"
    INTEGRATED = "INTEGRATED"
    VALIDATED = "VALIDATED"
    PRODUCTIONIZED = "PRODUCTIONIZED"


class ChangeType(StrEnum):
    NEW_CAPABILITY = "NEW_CAPABILITY"
    ENHANCEMENT = "ENHANCEMENT"
    REFACTOR = "REFACTOR"
    BUG_FIX = "BUG_FIX"
    MIGRATION = "MIGRATION"
    TEST_MATURATION = "TEST_MATURATION"
    DOCUMENTATION = "DOCUMENTATION"
    OPERATIONS = "OPERATIONS"
    REMOVAL = "REMOVAL"


class ObservedEvidence(BaseModel):
    id: str
    kind: EvidenceKind
    label: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    symbol: str | None = None
    commit_hash: str | None = None
    observed_at: datetime | None = None
    detail: str | None = None


class CodeEntity(BaseModel):
    id: str
    type: EntityType
    name: str
    qualified_name: str
    file_path: str
    line_start: int = 1
    line_end: int = 1
    language: str
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeRelationship(BaseModel):
    source_id: str
    target_id: str
    type: RelationshipType
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    inferred: bool = False


class CommitRecord(BaseModel):
    hash: str
    short_hash: str
    timestamp: datetime
    author: str
    subject: str
    changed_paths: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    change_type: ChangeType = ChangeType.ENHANCEMENT


class MaturitySignals(BaseModel):
    implementation: bool = False
    reachable: bool = False
    exposed: bool = False
    tests: bool = False
    validation: bool = False
    operations: bool = False
    documentation: bool = False
    monitoring: bool = False


class Capability(BaseModel):
    id: str
    name: str
    description: str
    category: CanonicalCategory
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    commit_hashes: list[str] = Field(default_factory=list)
    first_seen: datetime | None = None
    last_changed: datetime | None = None
    maturity: MaturityState
    maturity_signals: MaturitySignals
    confidence: float = Field(ge=0, le=1)
    reasoning_summary: str


class TimelineEvent(BaseModel):
    id: str
    capability_id: str
    timestamp: datetime
    change_type: ChangeType
    title: str
    summary: str
    commit_hash: str
    evidence_ids: list[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    group: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    confidence: float = Field(default=1, ge=0, le=1)
    inferred: bool = False


class GraphProjection(BaseModel):
    label: str
    description: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    truncated: bool = False


class CategorySummary(BaseModel):
    category: CanonicalCategory
    capability_count: int
    evidence_count: int


class RepositorySummary(BaseModel):
    owner: str
    name: str
    url: str
    default_branch: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    history_start: datetime | None = None
    history_end: datetime | None = None
    files_analyzed: int = 0
    source_bytes: int = 0


class AnalysisResult(BaseModel):
    id: str
    repository: RepositorySummary
    evidence: list[ObservedEvidence]
    entities: list[CodeEntity]
    relationships: list[CodeRelationship]
    commits: list[CommitRecord]
    capabilities: list[Capability]
    timeline: list[TimelineEvent]
    categories: list[CategorySummary]
    capability_graph: GraphProjection
    code_graph: GraphProjection
    workflow_graph: GraphProjection
    data_graph: GraphProjection
    warnings: list[str] = Field(default_factory=list)
    semantic_mode: str = "deterministic"


class AnalysisRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=300)


class HealthResponse(BaseModel):
    status: str = "ok"


class AnalysisSummary(BaseModel):
    id: str
    repository: RepositorySummary
    capability_count: int
