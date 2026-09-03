from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from app.analysis.behaviors import build_behavior_summaries
from app.ingestion.repository import GitHubRepository
from app.service import AnalysisService
from app.taxonomy import load_lens_set

BENCHMARK_FIXTURES = {
    "crud_admin": (
        "customer",
        """from pydantic import BaseModel
class CustomerRecord(BaseModel):
    customer_name: str
    account_status: str
def search_customers(records, query):
    return [record for record in records if query in record.customer_name]
def update_customer_status(record, status):
    record.account_status = status
    return record
def save_customer_record(record):
    customer_database.write(record)
def manage_customer_account(record, query, status):
    selected = search_customers([record], query)
    save_customer_record(update_customer_status(selected[0], status))
    return selected
""",
    ),
    "scientific_numerical": (
        "wavefield|boundary",
        """def calculate_boundary_conditions(grid, velocity):
    return grid * velocity
def solve_wavefield_step(grid, boundary):
    return grid + boundary
def simulate_wavefield(grid, velocity, steps):
    boundary = calculate_boundary_conditions(grid, velocity)
    return [solve_wavefield_step(grid, boundary) for _ in range(steps)]
def export_wavefield_samples(samples):
    writefile('wavefield-samples.csv', samples)
""",
    ),
    "developer_cli": (
        "dependency",
        """def scan_dependencies(package_graph):
    return list(package_graph.edges)
def detect_dependency_cycles(edges):
    return [edge for edge in edges if edge[0] == edge[1]]
def format_dependency_report(cycles):
    return '\\n'.join(map(str, cycles))
def run_dependency_audit(package_graph):
    edges = scan_dependencies(package_graph)
    return format_dependency_report(detect_dependency_cycles(edges))
def main():
    print(run_dependency_audit(load_package_graph()))
""",
    ),
    "ml_inference": (
        "churn",
        """def load_churn_model(model_path):
    return model_registry.load(model_path)
def encode_customer_features(customer_history):
    return feature_encoder.transform(customer_history)
def predict_customer_churn(model, customer_history):
    features = encode_customer_features(customer_history)
    return model.predict(features)
def explain_churn_prediction(model, customer_history):
    return {'churn_probability': predict_customer_churn(model, customer_history)}
""",
    ),
    "event_automation": (
        "order",
        """def enqueue_order_fulfillment(order_event):
    fulfillment_queue.write(order_event)
def retry_failed_delivery(order_event):
    return enqueue_order_fulfillment(order_event)
def send_order_notification(order_event):
    notification_client.publish(order_event)
def handle_order_created_event(order_event):
    enqueue_order_fulfillment(order_event)
    send_order_notification(order_event)
""",
    ),
    "data_processing": (
        "sensor",
        """def ingest_sensor_csv(uploaded_file):
    return csv_reader.parse(uploaded_file)
def normalize_sensor_rows(rows):
    return [dict(row, temperature=float(row['temperature'])) for row in rows]
def aggregate_daily_sensor_metrics(rows):
    return metrics.aggregate(rows)
def export_sensor_parquet(uploaded_file):
    rows = normalize_sensor_rows(ingest_sensor_csv(uploaded_file))
    return parquet_writer.write(aggregate_daily_sensor_metrics(rows))
""",
    ),
    "backend_service": (
        "session|access|audit",
        """from fastapi import FastAPI
app = FastAPI()
def validate_access_token(token):
    if not token: raise ValueError('access token required')
    return token
def authorize_session(token, permissions):
    return validate_access_token(token) in permissions
def persist_audit_record(session_id, allowed):
    audit_database.write({'session': session_id, 'allowed': allowed})
@app.post('/sessions/verify')
def verify_session(request):
    allowed = authorize_session(request.token, request.permissions)
    persist_audit_record(request.session_id, allowed)
    return {'allowed': allowed}
""",
    ),
    "library_framework": (
        "extension|renderer|middleware",
        """class ExtensionRegistry:
    def register_renderer(self, format_name, renderer):
        self.renderers[format_name] = renderer
    def resolve_renderer(self, format_name):
        return self.renderers[format_name]
def compose_middleware(handlers):
    def pipeline(payload):
        for handler in handlers: payload = handler(payload)
        return payload
    return pipeline
def execute_extension(registry, format_name, payload):
    renderer = registry.resolve_renderer(format_name)
    return compose_middleware([renderer])(payload)
""",
    ),
    "unfamiliar_domain": (
        "orbital|trajectory|ephemeris",
        """def calculate_orbital_transfer(position, velocity, target_orbit):
    return orbital_solver.solve(position, velocity, target_orbit)
def integrate_trajectory(initial_state, maneuver, duration):
    return trajectory_integrator.propagate(initial_state, maneuver, duration)
def simulate_spacecraft_transfer(initial_state, target_orbit):
    maneuver = calculate_orbital_transfer(*initial_state, target_orbit)
    return integrate_trajectory(initial_state, maneuver, 86400)
def export_ephemeris(trajectory):
    return ephemeris_writer.write(trajectory)
""",
    ),
}


def _repository(root: Path, files: dict[str, str]) -> Path:
    repository = root / "repository"
    repository.mkdir(parents=True)
    for relative, content in files.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@roadtrace.test", "add", "."],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@roadtrace.test",
            "commit",
            "-m",
            "implement fixture behavior",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    return repository


def _analyze(repository: Path, settings):
    return AnalysisService(settings).analyze_path(
        repository,
        GitHubRepository(
            owner="reasoning-fixtures",
            name=repository.parent.name,
            url="https://github.com/reasoning-fixtures/unseen-domain",
        ),
    )


@pytest.mark.parametrize(
    ("domain", "expected_term", "source"),
    [(domain, values[0], values[1]) for domain, values in BENCHMARK_FIXTURES.items()],
)
def test_open_world_inference_generalizes_across_unseen_domains(
    tmp_path: Path,
    settings,
    domain: str,
    expected_term: str,
    source: str,
) -> None:
    repository = _repository(
        tmp_path,
        {
            f"src/{domain}.py": source,
            f"tests/test_{domain}.py": (
                f"from src.{domain} import *\n"
                f"def test_{expected_term.split('|')[0]}_behavior():\n"
                f"    assert '{expected_term.split('|')[0]}'\n"
            ),
        },
    )
    result = _analyze(repository, settings)
    names = " ".join(item.name for item in result.capabilities).casefold()

    assert any(term in names for term in expected_term.split("|"))
    assert result.behaviors and result.observations
    assert any(item.mechanism_types for item in result.behaviors)
    assert all(item.evidence_ids and item.observation_ids for item in result.capabilities)
    assert len(result.capabilities) < len(result.entities)
    assert len({item.name.casefold() for item in result.capabilities}) == len(result.capabilities)
    active_lens_ids = {item.id for item in result.lens_set.lenses if item.status == "ACTIVE"}
    assert all(item.primary_lens in active_lens_ids for item in result.capabilities)
    capability_ids = {item.id for item in result.capabilities}
    assert all(
        item.parent_id is None or item.parent_id in capability_ids for item in result.capabilities
    )
    capability_by_id = {item.id: item for item in result.capabilities}
    for capability in result.capabilities:
        seen: set[str] = set()
        current = capability
        while current.parent_id is not None:
            assert current.id not in seen
            seen.add(current.id)
            current = capability_by_id[current.parent_id]
    assert all(
        item.first_seen is None or item.last_changed is None or item.first_seen <= item.last_changed
        for item in result.capabilities
    )
    states_by_capability: dict[str, list] = {}
    for state in result.capability_states:
        states_by_capability.setdefault(state.capability_id, []).append(state)
    assert all(
        [item.timestamp for item in states] == sorted(item.timestamp for item in states)
        for states in states_by_capability.values()
    )
    assert not {
        "json engine",
        "api surface",
        "react component",
        "helper utilities",
        "test folder",
    }.intersection(item.name.casefold() for item in result.capabilities)


def test_identifier_obfuscation_preserves_structure_backed_domain_signal(
    tmp_path: Path, settings
) -> None:
    meaningful = _repository(
        tmp_path / "meaningful",
        {
            "src/inventory.jsx": """export function loadInventoryLevels() {
  return JSON.parse(localStorage.getItem('inventory-levels') || '[]');
}
export function replenishInventory(items) { return items.filter(item => item.stock < 4); }
export function InventoryConsole() {
  const items = replenishInventory(loadInventoryLevels());
  return <main><h1>Inventory replenishment</h1><button>Replenish stock</button></main>;
}
"""
        },
    )
    obfuscated = _repository(
        tmp_path / "obfuscated",
        {
            "src/a.jsx": """export function fn_a() {
  return JSON.parse(localStorage.getItem('inventory-levels') || '[]');
}
export function fn_b(x) { return x.filter(y => y.stock < 4); }
export function Panel() {
  const z = fn_b(fn_a());
  return <main><h1>Inventory replenishment</h1><button>Replenish stock</button></main>;
}
"""
        },
    )
    meaningful_result = _analyze(meaningful, settings)
    obfuscated_result = _analyze(obfuscated, settings)

    for result in (meaningful_result, obfuscated_result):
        assert "inventory" in " ".join(item.name for item in result.capabilities).casefold()
        assert any(item.supporting_relationships for item in result.behaviors)
    meaningful_lenses = {
        lens
        for item in meaningful_result.capabilities
        for lens in [item.primary_lens, *item.secondary_lenses]
    }
    obfuscated_lenses = {
        lens
        for item in obfuscated_result.capabilities
        for lens in [item.primary_lens, *item.secondary_lenses]
    }
    assert meaningful_lenses.intersection(obfuscated_lenses)


def test_structure_ablation_lowers_behavior_confidence(tmp_path: Path, settings) -> None:
    repository = _repository(
        tmp_path,
        {"src/workflow.py": BENCHMARK_FIXTURES["event_automation"][1]},
    )
    result = _analyze(repository, settings)
    without_relationships = build_behavior_summaries(
        result.entities,
        [],
        result.evidence,
        lens_set=result.lens_set,
        use_relationships=False,
    )
    full_confidence = sum(item.confidence_dimensions.behavior for item in result.behaviors) / len(
        result.behaviors
    )
    ablated_confidence = sum(
        item.confidence_dimensions.behavior for item in without_relationships
    ) / len(without_relationships)
    assert full_confidence > ablated_confidence


def test_document_claims_cannot_create_or_override_capabilities(tmp_path: Path, settings) -> None:
    repository = _repository(
        tmp_path,
        {
            "src/invoice.py": """def calculate_invoice_total(line_items):
    return sum(item.amount for item in line_items)
def validate_invoice_total(total):
    if total < 0: raise ValueError('invoice total must be positive')
    return total
""",
            "README.md": (
                "# Payroll automation\n\nThe product performs payroll, hiring, route planning, "
                "and medical diagnosis. These are future ideas only.\n"
            ),
        },
    )
    result = _analyze(repository, settings)
    names = " ".join(item.name for item in result.capabilities).casefold()
    assert "invoice" in names
    assert all(term not in names for term in ("payroll", "hiring", "medical", "route"))
    claims = [item for item in result.observations if item.kind == "DOCUMENT_CLAIM"]
    assert claims
    assert not any(
        set(item.observation_ids).intersection({claim.id for claim in claims})
        for item in result.capabilities
    )


def test_lens_sets_are_versioned_replaceable_and_deprecatable(tmp_path: Path, settings) -> None:
    config = tmp_path / "lenses.json"
    config.write_text(
        json.dumps(
            {
                "id": "team-projection",
                "version": "3.2",
                "lenses": [
                    {
                        "id": "customer-value",
                        "label": "Customer Value",
                        "description": "User-visible value streams.",
                        "signals": ["interaction", "manage", "search"],
                    },
                    {
                        "id": "retired-view",
                        "label": "Retired View",
                        "description": "A retained historical projection.",
                        "status": "DEPRECATED",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    lens_set = load_lens_set(config)
    assert lens_set.version == "3.2"
    assert lens_set.lenses[1].status == "DEPRECATED"

    repository = _repository(
        tmp_path / "custom",
        {"src/customers.py": BENCHMARK_FIXTURES["crud_admin"][1]},
    )
    result = _analyze(repository, replace(settings, lens_config_path=config))
    assert {item.category for item in result.categories} == {"Customer Value"}
    assert all(item.primary_lens == "customer-value" for item in result.capabilities)


def test_provenance_chain_and_confidence_dimensions_are_complete(
    media_semantic_repository: Path, settings
) -> None:
    result = _analyze(media_semantic_repository, settings)
    evidence_ids = {item.id for item in result.evidence}
    observation_ids = {item.id for item in result.observations}
    behavior_ids = {item.id for item in result.behaviors}
    assert all(set(item.evidence_ids).issubset(evidence_ids) for item in result.observations)
    assert all(set(item.observation_ids).issubset(observation_ids) for item in result.behaviors)
    assert all(set(item.behavior_ids).issubset(behavior_ids) for item in result.capabilities)
    assert all(set(item.observation_ids).issubset(observation_ids) for item in result.capabilities)
    assert any(item.traits for item in result.capabilities)
    assert any(item.knowledge_quality is not None for item in result.capabilities)
    assert all(
        set(trait.evidence_ids).issubset(evidence_ids)
        for capability in result.capabilities
        for trait in capability.traits
    )
    assert all(set(state.behavior_ids).issubset(behavior_ids) for state in result.capability_states)
    assert all(
        0 <= value <= 1
        for capability in result.capabilities
        for value in capability.confidence_dimensions.model_dump().values()
    )
