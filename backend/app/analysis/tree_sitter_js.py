from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from app.analysis.languages import (
    LanguageAnalysis,
    PendingRelationship,
    build_entity,
    record_semantic_signal,
)
from app.domain import CodeEntity, CodeRelationship, EntityType, EvidenceKind, RelationshipType
from app.ingestion.repository import SourceFile


@dataclass(frozen=True, slots=True)
class _Definition:
    node: Node
    entity: CodeEntity


def _new_parser(language: Language) -> Parser:
    try:
        return Parser(language)
    except TypeError:
        parser = Parser()
        parser.language = language
        return parser


class JavaScriptTypeScriptAnalyzer:
    languages = frozenset({"JavaScript", "TypeScript"})

    def __init__(self) -> None:
        self.parsers = {
            "javascript": _new_parser(Language(tree_sitter_javascript.language())),
            "typescript": _new_parser(Language(tree_sitter_typescript.language_typescript())),
            "tsx": _new_parser(Language(tree_sitter_typescript.language_tsx())),
        }

    def analyze(self, source_file: SourceFile) -> LanguageAnalysis:
        result = LanguageAnalysis()
        parser_name = (
            "tsx"
            if Path(source_file.path).suffix.lower() == ".tsx"
            else "typescript"
            if source_file.language == "TypeScript"
            else "javascript"
        )
        source = source_file.content.encode()
        tree = self.parsers[parser_name].parse(source)
        if tree.root_node.has_error:
            result.warnings.append(
                f"Tree-sitter recovered from syntax errors in {source_file.path}"
            )

        module_name = Path(source_file.path).with_suffix("").as_posix().replace("/", ".")
        module, evidence = build_entity(
            entity_type=EntityType.MODULE,
            name=Path(source_file.path).stem,
            qualified_name=module_name,
            source_file=source_file,
            line_start=1,
            line_end=max(1, tree.root_node.end_point.row + 1),
        )
        result.entities.append(module)
        result.evidence.append(evidence)
        definitions: list[_Definition] = [_Definition(tree.root_node, module)]

        for node in _walk(tree.root_node):
            created = self._definition(node, source, source_file, definitions)
            if created is not None:
                entity, entity_evidence, parent = created
                definitions.append(_Definition(node, entity))
                result.entities.append(entity)
                result.evidence.append(entity_evidence)
                result.relationships.append(
                    CodeRelationship(
                        source_id=parent.id,
                        target_id=entity.id,
                        type=RelationshipType.CONTAINS,
                        confidence=1,
                        evidence_ids=entity.evidence_ids,
                    )
                )

        route_definitions: list[_Definition] = []
        for node in _walk(tree.root_node):
            if node.type != "call_expression":
                continue
            function = node.child_by_field_name("function")
            arguments = node.child_by_field_name("arguments")
            method = _text(function, source).rsplit(".", 1)[-1].upper()
            route = _first_string(arguments, source) if arguments is not None else None
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "ROUTE"}:
                continue
            if route is None or not route.startswith("/"):
                continue
            parent = _nearest_owner(node, definitions)
            qualified_name = (
                f"{module.qualified_name}.route:{method}:{route}:{node.start_point.row + 1}"
            )
            endpoint, endpoint_evidence = build_entity(
                entity_type=EntityType.API_ENDPOINT,
                name=f"{method} {route}",
                qualified_name=qualified_name,
                source_file=source_file,
                line_start=node.start_point.row + 1,
                line_end=node.end_point.row + 1,
                metadata={"entrypoint": True, "route_method": method, "route_path": route},
            )
            result.entities.append(endpoint)
            result.evidence.append(endpoint_evidence)
            record_semantic_signal(
                result,
                endpoint,
                source_file,
                kind="api_route",
                value=f"{method} {route}",
                line=node.start_point.row + 1,
                evidence_kind=EvidenceKind.API,
            )
            route_definitions.append(_Definition(node, endpoint))
            result.relationships.extend(
                [
                    CodeRelationship(
                        source_id=parent.id,
                        target_id=endpoint.id,
                        type=RelationshipType.CONTAINS,
                        confidence=1,
                        evidence_ids=endpoint.evidence_ids,
                    ),
                    CodeRelationship(
                        source_id=module.id,
                        target_id=endpoint.id,
                        type=RelationshipType.EXPOSES,
                        confidence=1,
                        evidence_ids=endpoint.evidence_ids,
                    ),
                ]
            )
        definitions.extend(route_definitions)

        test_definitions: list[_Definition] = []
        for node in _walk(tree.root_node):
            if node.type != "call_expression":
                continue
            function = node.child_by_field_name("function")
            arguments = node.child_by_field_name("arguments")
            function_name = _text(function, source).rsplit(".", 1)[-1]
            label = _first_string(arguments, source) if arguments is not None else None
            if function_name not in {"describe", "it", "test", "spec"} or not label:
                continue
            parent = _nearest_owner(node, definitions)
            test, test_evidence = build_entity(
                entity_type=EntityType.TEST,
                name=label,
                qualified_name=f"{module.qualified_name}.test:{label}:{node.start_point.row + 1}",
                source_file=source_file,
                line_start=node.start_point.row + 1,
                line_end=node.end_point.row + 1,
                metadata={"test_label": label},
            )
            result.entities.append(test)
            result.evidence.append(test_evidence)
            record_semantic_signal(
                result,
                test,
                source_file,
                kind="test_name",
                value=label,
                line=node.start_point.row + 1,
                evidence_kind=EvidenceKind.TEST,
            )
            result.relationships.append(
                CodeRelationship(
                    source_id=parent.id,
                    target_id=test.id,
                    type=RelationshipType.CONTAINS,
                    confidence=1,
                    evidence_ids=test.evidence_ids,
                )
            )
            test_definitions.append(_Definition(node, test))
        definitions.extend(test_definitions)

        for node in _walk(tree.root_node):
            owner = _nearest_owner(node, definitions)
            if node.type == "import_statement":
                target = node.child_by_field_name("source")
                if target is not None:
                    result.pending_relationships.append(
                        PendingRelationship(
                            source_id=owner.id,
                            target_name=_text(target, source).strip("'\""),
                            type=RelationshipType.IMPORTS,
                            confidence=1,
                            evidence_ids=tuple(owner.evidence_ids),
                        )
                    )
            elif node.type == "call_expression":
                function = node.child_by_field_name("function")
                if function is None:
                    continue
                name = _text(function, source)
                called = owner.metadata.setdefault("called_symbols", [])
                if isinstance(called, list) and name not in called:
                    called.append(name)
                if name == "require":
                    arguments = node.child_by_field_name("arguments")
                    target = _first_string(arguments, source) if arguments is not None else None
                    if target:
                        result.pending_relationships.append(
                            PendingRelationship(
                                source_id=owner.id,
                                target_name=target,
                                type=RelationshipType.IMPORTS,
                                confidence=1,
                                evidence_ids=tuple(owner.evidence_ids),
                            )
                        )
                elif owner.id != module.id:
                    result.pending_relationships.append(
                        PendingRelationship(
                            source_id=owner.id,
                            target_name=name,
                            type=(
                                RelationshipType.INSTANTIATES
                                if name.rsplit(".", 1)[-1][:1].isupper()
                                else RelationshipType.CALLS
                            ),
                            confidence=0.68,
                            evidence_ids=tuple(owner.evidence_ids),
                            inferred=True,
                        )
                    )
        self._record_semantic_signals(tree.root_node, source, source_file, definitions, result)
        return result

    def _record_semantic_signals(
        self,
        root: Node,
        source: bytes,
        source_file: SourceFile,
        definitions: list[_Definition],
        result: LanguageAnalysis,
    ) -> None:
        visible_attributes = {"aria-label", "label", "placeholder", "title"}
        data_operations = {
            "delete",
            "find",
            "findone",
            "insert",
            "query",
            "readfile",
            "save",
            "update",
            "writefile",
        }
        for node in _walk(root):
            owner = _nearest_owner(node, definitions)
            line = node.start_point.row + 1
            if node.type == "jsx_text":
                record_semantic_signal(
                    result,
                    owner,
                    source_file,
                    kind="ui_text",
                    value=_text(node, source),
                    line=line,
                    evidence_kind=EvidenceKind.UI,
                )
                continue
            if node.type == "jsx_attribute":
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")
                name = _text(name_node, source)
                if name in visible_attributes and value_node is not None:
                    record_semantic_signal(
                        result,
                        owner,
                        source_file,
                        kind="form_label" if name in {"label", "placeholder"} else "ui_text",
                        value=_text(value_node, source).strip("'\"{}"),
                        line=line,
                        evidence_kind=EvidenceKind.UI,
                    )
                continue
            if node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")
                name = _text(name_node, source)
                if name.isupper() and value_node is not None:
                    values = _string_literals(value_node, source)[:8]
                    if values:
                        record_semantic_signal(
                            result,
                            owner,
                            source_file,
                            kind="constant",
                            value=f"{name.replace('_', ' ')}: {', '.join(values)}",
                            line=line,
                        )
                continue
            if node.type == "member_expression":
                value = _text(node, source)
                match = re.search(r"(?:process|import\.meta)\.env\.([A-Z][A-Z0-9_]*)", value)
                if match:
                    record_semantic_signal(
                        result,
                        owner,
                        source_file,
                        kind="environment_variable",
                        value=match.group(1),
                        line=line,
                    )
                continue
            if node.type != "call_expression":
                continue
            function = node.child_by_field_name("function")
            arguments = node.child_by_field_name("arguments")
            function_name = _text(function, source)
            first_argument = _first_argument_text(arguments, source)
            lowered = function_name.casefold()
            if "localstorage." in lowered or "indexeddb." in lowered:
                record_semantic_signal(
                    result,
                    owner,
                    source_file,
                    kind="browser_storage",
                    value=f"{function_name}: {first_argument or 'stored application data'}",
                    line=line,
                )
            tail = lowered.rsplit(".", 1)[-1]
            if tail in data_operations:
                record_semantic_signal(
                    result,
                    owner,
                    source_file,
                    kind="data_operation",
                    value=function_name,
                    line=line,
                )
            if tail in {"error", "typeerror", "rangeerror", "alert"} and first_argument:
                record_semantic_signal(
                    result,
                    owner,
                    source_file,
                    kind="error_message",
                    value=first_argument,
                    line=line,
                )

    def _definition(
        self,
        node: Node,
        source: bytes,
        source_file: SourceFile,
        existing: list[_Definition],
    ) -> tuple[CodeEntity, Any, CodeEntity] | None:
        name_node: Node | None = None
        name = ""
        entity_type: EntityType | None = None
        value_node = node
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            name = _text(name_node, source) if name_node else "anonymous_class"
            entity_type = (
                EntityType.SCHEMA if name.endswith(("Schema", "Model")) else EntityType.CLASS
            )
        elif node.type in {"function_declaration", "generator_function_declaration"}:
            name_node = node.child_by_field_name("name")
            name = _text(name_node, source) if name_node else "anonymous_function"
            entity_type = _js_function_type(name, source_file.path)
        elif node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            name = _text(name_node, source) if name_node else "anonymous_method"
            entity_type = EntityType.METHOD
        elif node.type == "variable_declarator":
            value_node = node.child_by_field_name("value") or node
            if value_node.type not in {"arrow_function", "function_expression"}:
                return None
            name_node = node.child_by_field_name("name")
            name = _text(name_node, source) if name_node else "anonymous_function"
            entity_type = _js_function_type(name, source_file.path)
        if entity_type is None:
            return None
        parent = _nearest_owner(node.parent or node, existing)
        qualified = f"{parent.qualified_name}.{name}"
        entrypoint = (
            entity_type == EntityType.UI_COMPONENT
            or name in {"main", "handler"}
            or name.startswith(("handle", "on", "run"))
        )
        entity, evidence = build_entity(
            entity_type=entity_type,
            name=name,
            qualified_name=qualified,
            source_file=source_file,
            line_start=node.start_point.row + 1,
            line_end=max(node.start_point.row + 1, value_node.end_point.row + 1),
            metadata={"entrypoint": entrypoint},
        )
        return entity, evidence, parent


def _js_function_type(name: str, file_path: str) -> EntityType:
    if name.startswith(("test", "it", "spec")) or ".test." in file_path or ".spec." in file_path:
        return EntityType.TEST
    if name[:1].isupper() and Path(file_path).suffix.lower() in {".jsx", ".tsx"}:
        return EntityType.UI_COMPONENT
    return EntityType.FUNCTION


def _walk(node: Node):
    stack = list(reversed(node.named_children))
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _nearest_owner(node: Node, definitions: list[_Definition]) -> CodeEntity:
    candidates = [
        definition
        for definition in definitions
        if definition.node.start_byte <= node.start_byte
        and definition.node.end_byte >= node.end_byte
    ]
    return min(candidates, key=lambda item: item.node.end_byte - item.node.start_byte).entity


def _first_string(node: Node, source: bytes) -> str | None:
    for child in node.named_children:
        if child.type in {"string", "string_fragment"}:
            return _text(child, source).strip("'\"")
    return None


def _first_argument_text(node: Node | None, source: bytes) -> str | None:
    if node is None or not node.named_children:
        return None
    return _text(node.named_children[0], source).strip("'\"`{}")


def _string_literals(node: Node, source: bytes) -> list[str]:
    values: list[str] = []
    nodes = [node]
    while nodes and len(values) < 12:
        current = nodes.pop()
        if current.type in {"string", "string_fragment", "template_string"}:
            value = _text(current, source).strip("'\"`")
            if value and value not in values:
                values.append(value)
            continue
        nodes.extend(reversed(current.named_children))
    return values
