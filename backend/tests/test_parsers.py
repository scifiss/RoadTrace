from pathlib import Path

from app.analysis.languages import PythonAstAnalyzer
from app.analysis.modeling import merge_and_resolve
from app.analysis.tree_sitter_js import JavaScriptTypeScriptAnalyzer
from app.domain import EntityType, EvidenceKind, RelationshipType
from app.ingestion.repository import SourceFile


def source(path: str, language: str, content: str) -> SourceFile:
    return SourceFile(
        path=path,
        absolute_path=Path(path),
        language=language,
        size=len(content),
        content=content,
    )


def test_python_ast_extracts_entities_routes_schemas_and_calls() -> None:
    analysis = PythonAstAnalyzer().analyze(
        source(
            "app/api.py",
            "Python",
            """import os
from pydantic import BaseModel
class InputModel(BaseModel):
    value: str
def calculate(value):
    if not value:
        raise ValueError('A calculation value is required')
    model = os.getenv('CALCULATION_MODEL')
    return len(value)
@router.post('/calculate')
def endpoint(payload: InputModel):
    return calculate(payload.value)
""",
        )
    )
    types = {entity.type for entity in analysis.entities}
    assert EntityType.SCHEMA in types
    assert EntityType.API_ENDPOINT in types
    assert any(item.target_name == "calculate" for item in analysis.pending_relationships)
    schema = next(item for item in analysis.entities if item.type == EntityType.SCHEMA)
    endpoint = next(item for item in analysis.entities if item.type == EntityType.API_ENDPOINT)
    assert schema.metadata["fields"] == ["value"]
    assert endpoint.metadata["route_paths"] == ["/calculate"]
    labels = {item.label for item in analysis.evidence}
    assert "Environment Variable: CALCULATION_MODEL" in labels
    assert "Error Message: A calculation value is required" in labels


def test_typescript_tree_sitter_extracts_components_imports_and_calls() -> None:
    analysis = JavaScriptTypeScriptAnalyzer().analyze(
        source(
            "web/App.tsx",
            "TypeScript",
            """import React from 'react';
export function Dashboard() {
  const savedRoads = localStorage.getItem('road-plans');
  const handleClick = () => loadRoads();
  return <section><h1>Route planner</h1><button onClick={handleClick}>Load roads</button></section>;
}
function loadRoads() { return []; }
""",
        )
    )
    assert any(entity.type == EntityType.UI_COMPONENT for entity in analysis.entities)
    assert any(item.type == RelationshipType.IMPORTS for item in analysis.pending_relationships)
    assert any(item.target_name == "loadRoads" for item in analysis.pending_relationships)
    evidence_labels = {item.label for item in analysis.evidence}
    assert "Browser Storage: localStorage.getItem: road-plans" in evidence_labels
    assert "Ui Text: Route planner" in evidence_labels
    assert "Ui Text: Load roads" in evidence_labels


def test_javascript_tree_sitter_extracts_api_routes() -> None:
    analysis = JavaScriptTypeScriptAnalyzer().analyze(
        source(
            "server/routes.ts",
            "TypeScript",
            "router.post('/roads', createRoad);\nfunction createRoad() { return {}; }\n",
        )
    )
    assert any(
        entity.type == EntityType.API_ENDPOINT and entity.name == "POST /roads"
        for entity in analysis.entities
    )


def test_javascript_tests_become_behavioral_evidence() -> None:
    analysis = JavaScriptTypeScriptAnalyzer().analyze(
        source(
            "tests/anomaly.test.ts",
            "TypeScript",
            "describe('weighted anomaly score', () => { "
            "it('explains missing signals', () => {}); });",
        )
    )
    tests = [item for item in analysis.entities if item.type == EntityType.TEST]
    assert {item.name for item in tests} == {
        "weighted anomaly score",
        "explains missing signals",
    }
    assert any(item.kind == EvidenceKind.TEST for item in analysis.evidence)


def test_import_and_call_graph_resolves_internal_symbols() -> None:
    analyzer = PythonAstAnalyzer()
    engine = analyzer.analyze(source("pkg/engine.py", "Python", "def calculate():\n    return 1\n"))
    api = analyzer.analyze(
        source(
            "pkg/api.py",
            "Python",
            "from pkg.engine import calculate\ndef handler():\n    return calculate()\n",
        )
    )
    merged = merge_and_resolve([engine, api])
    names = {entity.id: entity.name for entity in merged.entities}
    assert any(
        relation.type == RelationshipType.CALLS
        and names[relation.source_id] == "handler"
        and names[relation.target_id] == "calculate"
        for relation in merged.relationships
    )
