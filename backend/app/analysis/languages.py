from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.domain import (
    CodeEntity,
    CodeRelationship,
    EntityType,
    EvidenceKind,
    ObservedEvidence,
    RelationshipType,
)
from app.ingestion.repository import SourceFile


def stable_id(prefix: str, *parts: object) -> str:
    value = "\x1f".join(str(part) for part in parts).encode()
    return f"{prefix}_{hashlib.blake2s(value, digest_size=10).hexdigest()}"


@dataclass(frozen=True, slots=True)
class PendingRelationship:
    source_id: str
    target_name: str
    type: RelationshipType
    confidence: float
    evidence_ids: tuple[str, ...] = ()
    inferred: bool = False


@dataclass(slots=True)
class LanguageAnalysis:
    entities: list[CodeEntity] = field(default_factory=list)
    relationships: list[CodeRelationship] = field(default_factory=list)
    pending_relationships: list[PendingRelationship] = field(default_factory=list)
    evidence: list[ObservedEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class LanguageAnalyzer(Protocol):
    languages: frozenset[str]

    def analyze(self, source_file: SourceFile) -> LanguageAnalysis: ...


def evidence_kind_for(entity_type: EntityType) -> EvidenceKind:
    return {
        EntityType.API_ENDPOINT: EvidenceKind.API,
        EntityType.SCHEMA: EvidenceKind.SCHEMA,
        EntityType.UI_COMPONENT: EvidenceKind.UI,
        EntityType.TEST: EvidenceKind.TEST,
        EntityType.CONFIGURATION: EvidenceKind.CONFIGURATION,
        EntityType.EXTERNAL_MODULE: EvidenceKind.DEPENDENCY,
    }.get(entity_type, EvidenceKind.SOURCE)


def build_entity(
    *,
    entity_type: EntityType,
    name: str,
    qualified_name: str,
    source_file: SourceFile,
    line_start: int,
    line_end: int,
    metadata: dict[str, object] | None = None,
) -> tuple[CodeEntity, ObservedEvidence]:
    entity_id = stable_id("ent", source_file.path, qualified_name, entity_type)
    evidence_id = stable_id("ev", entity_id)
    entity = CodeEntity(
        id=entity_id,
        type=entity_type,
        name=name,
        qualified_name=qualified_name,
        file_path=source_file.path,
        line_start=max(1, line_start),
        line_end=max(line_start, line_end),
        language=source_file.language,
        evidence_ids=[evidence_id],
        metadata=metadata or {},
    )
    evidence = ObservedEvidence(
        id=evidence_id,
        kind=evidence_kind_for(entity_type),
        label=f"{entity_type.value.replace('_', ' ').title()}: {qualified_name}",
        file_path=source_file.path,
        line_start=entity.line_start,
        line_end=entity.line_end,
        symbol=qualified_name,
        detail="Observed by static syntax analysis",
    )
    return entity, evidence


_SEMANTIC_TEXT_NOISE = {
    "button",
    "click",
    "close",
    "container",
    "div",
    "false",
    "label",
    "none",
    "null",
    "span",
    "submit",
    "true",
    "undefined",
}


def meaningful_semantic_text(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", value).strip(" \t\r\n'\"`{}[]();,")
    if not 3 <= len(cleaned) <= 180 or not any(character.isalpha() for character in cleaned):
        return None
    lowered = cleaned.casefold()
    if lowered in _SEMANTIC_TEXT_NOISE:
        return None
    if re.fullmatch(r"[#.\w-]+", cleaned) and (
        cleaned.startswith(("#", ".")) or any(char.isdigit() for char in cleaned)
    ):
        return None
    if cleaned.count("{") + cleaned.count("}") + cleaned.count(";") > 3:
        return None
    return cleaned


def record_semantic_signal(
    result: LanguageAnalysis,
    entity: CodeEntity,
    source_file: SourceFile,
    *,
    kind: str,
    value: str,
    line: int,
    evidence_kind: EvidenceKind = EvidenceKind.SEMANTIC,
) -> None:
    cleaned = meaningful_semantic_text(value)
    if cleaned is None:
        return
    signals = entity.metadata.setdefault("semantic_signals", [])
    if not isinstance(signals, list):
        signals = []
        entity.metadata["semantic_signals"] = signals
    signal = {"kind": kind, "value": cleaned}
    if signal in signals:
        return
    signals.append(signal)
    evidence_id = stable_id("evsignal", entity.id, kind, cleaned, line)
    entity.evidence_ids.append(evidence_id)
    result.evidence.append(
        ObservedEvidence(
            id=evidence_id,
            kind=evidence_kind,
            label=f"{kind.replace('_', ' ').title()}: {cleaned}",
            file_path=source_file.path,
            line_start=max(1, line),
            line_end=max(1, line),
            symbol=entity.qualified_name,
            detail="Observed directly in executable source",
        )
    )


def dotted_python_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted_python_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return None


class PythonAstAnalyzer(ast.NodeVisitor):
    languages = frozenset({"Python"})

    def analyze(self, source_file: SourceFile) -> LanguageAnalysis:
        self.source_file = source_file
        self.result = LanguageAnalysis()
        self.scope: list[CodeEntity] = []
        try:
            tree = ast.parse(source_file.content, filename=source_file.path, type_comments=True)
        except (SyntaxError, ValueError) as exc:
            self.result.warnings.append(f"Could not parse Python file {source_file.path}: {exc}")
            return self.result

        module_name = Path(source_file.path).with_suffix("").as_posix().replace("/", ".")
        module, evidence = build_entity(
            entity_type=EntityType.MODULE,
            name=Path(source_file.path).stem,
            qualified_name=module_name,
            source_file=source_file,
            line_start=1,
            line_end=max(1, len(source_file.content.splitlines())),
        )
        self.result.entities.append(module)
        self.result.evidence.append(evidence)
        self.scope.append(module)
        self.visit(tree)
        self.scope.pop()
        return self.result

    def _qualified(self, name: str) -> str:
        return f"{self.scope[-1].qualified_name}.{name}"

    def _append_entity(
        self,
        node: ast.AST,
        name: str,
        entity_type: EntityType,
        metadata: dict[str, object] | None = None,
    ) -> CodeEntity:
        entity, evidence = build_entity(
            entity_type=entity_type,
            name=name,
            qualified_name=self._qualified(name),
            source_file=self.source_file,
            line_start=getattr(node, "lineno", 1),
            line_end=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
            metadata=metadata,
        )
        parent = self.scope[-1]
        self.result.entities.append(entity)
        self.result.evidence.append(evidence)
        self.result.relationships.append(
            CodeRelationship(
                source_id=parent.id,
                target_id=entity.id,
                type=RelationshipType.CONTAINS,
                confidence=1,
                evidence_ids=entity.evidence_ids,
            )
        )
        return entity

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [name for base in node.bases if (name := dotted_python_name(base))]
        entity_type = (
            EntityType.SCHEMA
            if any(base.split(".")[-1] in {"BaseModel", "Model", "Schema"} for base in bases)
            or node.name.endswith(("Schema", "Model"))
            else EntityType.CLASS
        )
        entity = self._append_entity(node, node.name, entity_type, {"bases": bases})
        for base in bases:
            self.result.pending_relationships.append(
                PendingRelationship(
                    source_id=entity.id,
                    target_name=base,
                    type=RelationshipType.INHERITS,
                    confidence=0.95,
                    evidence_ids=tuple(entity.evidence_ids),
                )
            )
        self.scope.append(entity)
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        decorators = [name for item in node.decorator_list if (name := dotted_python_name(item))]
        route_methods: list[str] = []
        route_paths: list[str] = []
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = dotted_python_name(target)
            if name and name.rsplit(".", 1)[-1].lower() in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "route",
                "websocket",
            }:
                route_methods.append(name.rsplit(".", 1)[-1].upper())
                if (
                    isinstance(decorator, ast.Call)
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    route_paths.append(decorator.args[0].value)
        if route_methods:
            entity_type = EntityType.API_ENDPOINT
        elif node.name.startswith("test_"):
            entity_type = EntityType.TEST
        elif self.scope[-1].type in {EntityType.CLASS, EntityType.SCHEMA}:
            entity_type = EntityType.METHOD
        else:
            entity_type = EntityType.FUNCTION
        entrypoint = (
            bool(route_methods)
            or node.name in {"main", "cli"}
            or node.name.startswith(("handle_", "run_"))
        )
        entity = self._append_entity(
            node,
            node.name,
            entity_type,
            {
                "decorators": decorators,
                "route_methods": route_methods,
                "route_paths": route_paths,
                "entrypoint": entrypoint,
            },
        )
        if entity_type == EntityType.TEST:
            record_semantic_signal(
                self.result,
                entity,
                self.source_file,
                kind="test_name",
                value=node.name.replace("_", " "),
                line=node.lineno,
                evidence_kind=EvidenceKind.TEST,
            )
        for route_path in route_paths:
            record_semantic_signal(
                self.result,
                entity,
                self.source_file,
                kind="api_route",
                value=route_path,
                line=node.lineno,
                evidence_kind=EvidenceKind.API,
            )
        if route_methods:
            self.result.relationships.append(
                CodeRelationship(
                    source_id=self.scope[-1].id,
                    target_id=entity.id,
                    type=RelationshipType.EXPOSES,
                    confidence=1,
                    evidence_ids=entity.evidence_ids,
                )
            )
        self.scope.append(entity)
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._pending_import(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        self._pending_import(module)

    def _pending_import(self, module: str) -> None:
        if not module:
            return
        self.result.pending_relationships.append(
            PendingRelationship(
                source_id=self.scope[-1].id,
                target_name=module,
                type=RelationshipType.IMPORTS,
                confidence=1,
                evidence_ids=tuple(self.scope[-1].evidence_ids),
            )
        )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and self.scope[-1].type == EntityType.SCHEMA:
            fields = self.scope[-1].metadata.setdefault("fields", [])
            if isinstance(fields, list) and node.target.id not in fields:
                fields.append(node.target.id)
            record_semantic_signal(
                self.result,
                self.scope[-1],
                self.source_file,
                kind="schema_field",
                value=node.target.id.replace("_", " "),
                line=node.lineno,
                evidence_kind=EvidenceKind.SCHEMA,
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if not isinstance(target, ast.Name) or not target.id.isupper():
                continue
            values = _python_literal_strings(node.value)
            if values:
                record_semantic_signal(
                    self.result,
                    self.scope[-1],
                    self.source_file,
                    kind="constant",
                    value=f"{target.id.replace('_', ' ')}: {', '.join(values[:8])}",
                    line=node.lineno,
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = dotted_python_name(node.func)
        if target:
            called = self.scope[-1].metadata.setdefault("called_symbols", [])
            if isinstance(called, list) and target not in called:
                called.append(target)
            first_value = (
                node.args[0].value
                if node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                else None
            )
            tail = target.rsplit(".", 1)[-1].casefold()
            if first_value and tail in {"getenv", "get_environment_variable"}:
                record_semantic_signal(
                    self.result,
                    self.scope[-1],
                    self.source_file,
                    kind="environment_variable",
                    value=first_value,
                    line=node.lineno,
                )
            elif first_value and tail.endswith(("error", "exception")):
                record_semantic_signal(
                    self.result,
                    self.scope[-1],
                    self.source_file,
                    kind="error_message",
                    value=first_value,
                    line=node.lineno,
                )
        if target and self.scope[-1].type not in {EntityType.MODULE}:
            relation_type = (
                RelationshipType.INSTANTIATES
                if target.rsplit(".", 1)[-1][:1].isupper()
                else RelationshipType.CALLS
            )
            self.result.pending_relationships.append(
                PendingRelationship(
                    source_id=self.scope[-1].id,
                    target_name=target,
                    type=relation_type,
                    confidence=0.72,
                    evidence_ids=tuple(self.scope[-1].evidence_ids),
                    inferred=True,
                )
            )
        self.generic_visit(node)


def _python_literal_strings(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [
            item.value
            for item in node.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        ]
    return []


def load_default_analyzers() -> list[LanguageAnalyzer]:
    from app.analysis.tree_sitter_js import JavaScriptTypeScriptAnalyzer

    return [PythonAstAnalyzer(), JavaScriptTypeScriptAnalyzer()]
