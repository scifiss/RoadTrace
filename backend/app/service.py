from __future__ import annotations

import uuid
from collections import Counter
from pathlib import Path

from app.analysis.history import GitHistoryAnalyzer
from app.analysis.languages import LanguageAnalysis, load_default_analyzers
from app.analysis.modeling import (
    CapabilityInferer,
    build_graphs,
    commit_evidence,
    merge_and_resolve,
    support_entities,
)
from app.config import Settings
from app.domain import AnalysisResult, RepositorySummary
from app.ingestion.repository import (
    GitHubRepository,
    GitRunner,
    PublicGitHubAcquirer,
    collect_source_files,
)
from app.llm.semantic import SemanticRefiner
from app.storage.sqlite import AnalysisStore


class AnalysisService:
    def __init__(self, settings: Settings, store: AnalysisStore | None = None) -> None:
        self.settings = settings
        self.store = store
        self.acquirer = PublicGitHubAcquirer(settings)
        self.history = GitHistoryAnalyzer(
            GitRunner(settings.git_timeout_seconds), settings.max_commits
        )
        self.analyzers = load_default_analyzers()
        self.semantic = SemanticRefiner(settings)

    def analyze_url(self, repository_url: str) -> AnalysisResult:
        with self.acquirer.acquire(repository_url) as acquired:
            return self.analyze_path(acquired.path, acquired.identity)

    def analyze_path(self, path: Path, identity: GitHubRepository) -> AnalysisResult:
        source_files, file_warnings = collect_source_files(path, self.settings)
        chunks: list[LanguageAnalysis] = [support_entities(source_files)]
        for source_file in source_files:
            for analyzer in self.analyzers:
                if source_file.language in analyzer.languages:
                    chunks.append(analyzer.analyze(source_file))
                    break
        observed = merge_and_resolve(chunks)
        commits, default_branch, history_warnings = self.history.analyze(path)
        all_evidence = [*observed.evidence, *commit_evidence(commits)]
        capabilities, timeline, categories = CapabilityInferer().infer(
            observed.entities, observed.relationships, all_evidence, commits
        )
        capabilities, semantic_warnings, semantic_mode = self.semantic.refine(
            capabilities, observed.entities, all_evidence
        )
        capability_graph, code_graph, workflow_graph, data_graph = build_graphs(
            observed.entities,
            observed.relationships,
            capabilities,
            self.settings.max_graph_nodes,
            self.settings.max_workflow_depth,
        )
        language_bytes = Counter(
            {
                language: sum(item.size for item in source_files if item.language == language)
                for language in {item.language for item in source_files}
                if language not in {"Documentation", "Configuration"}
            }
        )
        result = AnalysisResult(
            id=str(uuid.uuid4()),
            repository=RepositorySummary(
                owner=identity.owner,
                name=identity.name,
                url=identity.url,
                default_branch=default_branch,
                languages=dict(language_bytes.most_common()),
                history_start=commits[0].timestamp if commits else None,
                history_end=commits[-1].timestamp if commits else None,
                files_analyzed=len(source_files),
                source_bytes=sum(item.size for item in source_files),
            ),
            evidence=all_evidence,
            entities=observed.entities,
            relationships=observed.relationships,
            commits=commits,
            capabilities=capabilities,
            timeline=timeline,
            categories=categories,
            capability_graph=capability_graph,
            code_graph=code_graph,
            workflow_graph=workflow_graph,
            data_graph=data_graph,
            warnings=[
                *file_warnings,
                *observed.warnings,
                *history_warnings,
                *semantic_warnings,
            ],
            semantic_mode=semantic_mode,
        )
        if self.store is not None:
            self.store.save(result)
        return result
