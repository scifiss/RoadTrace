export type LensLabel = string

export interface ConfidenceDimensions {
  evidence: number
  behavior: number
  semantic: number
  temporal: number
}

export interface CapabilityTrait {
  id: string
  label: string
  evidence_ids: string[]
  confidence: number
}

export interface KnowledgeQuality {
  breadth: string | null
  depth: string | null
  executability: string | null
  grounding: string | null
  freshness: string | null
  evidence_ids: string[]
  confidence: number | null
}

export interface LensDefinition {
  id: string
  label: string
  description: string
  version: string
  status: string
  aliases: string[]
  signals: string[]
}

export interface LensSet {
  id: string
  version: string
  lenses: LensDefinition[]
}

export interface RepositorySummary {
  owner: string
  name: string
  url: string
  default_branch: string | null
  languages: Record<string, number>
  analyzed_at: string
  history_start: string | null
  history_end: string | null
  files_analyzed: number
  source_bytes: number
}

export interface Evidence {
  id: string
  kind: string
  label: string
  file_path: string | null
  line_start: number | null
  line_end: number | null
  symbol: string | null
  commit_hash: string | null
  observed_at: string | null
  detail: string | null
  source_kind: string | null
  source_revision: string | null
}

export interface Observation {
  id: string
  kind: string
  summary: string
  evidence_ids: string[]
  entity_ids: string[]
  relationship_ids: string[]
  inputs: string[]
  outputs: string[]
  terms: string[]
  structural: boolean
  confidence: number
}

export interface Entity {
  id: string
  type: string
  name: string
  qualified_name: string
  file_path: string
  line_start: number
  line_end: number
  language: string
  evidence_ids: string[]
  metadata: Record<string, unknown>
}

export interface MaturitySignals {
  implementation: boolean
  reachable: boolean
  exposed: boolean
  tests: boolean
  validation: boolean
  operations: boolean
  documentation: boolean
  monitoring: boolean
}

export interface Capability {
  id: string
  name: string
  description: string
  primary_lens: string
  secondary_lenses: string[]
  category: LensLabel
  parent_id: string | null
  child_ids: string[]
  behavior_ids: string[]
  aliases: string[]
  secondary_categories: LensLabel[]
  observation_ids: string[]
  traits: CapabilityTrait[]
  knowledge_quality: KnowledgeQuality | null
  entity_ids: string[]
  evidence_ids: string[]
  commit_hashes: string[]
  first_seen: string | null
  last_changed: string | null
  maturity: string
  maturity_signals: MaturitySignals
  confidence: number
  confidence_dimensions: ConfidenceDimensions
  reasoning_summary: string
}

export interface BehaviorSummary {
  id: string
  name: string
  description: string
  mechanism_types: string[]
  primary_lens: string
  secondary_lenses: string[]
  primary_category: LensLabel
  secondary_categories: LensLabel[]
  parent_name: string | null
  supporting_entity_ids: string[]
  supporting_relationships: string[]
  observation_ids: string[]
  evidence_ids: string[]
  observable_inputs: string[]
  observable_outputs: string[]
  ui_surfaces: string[]
  api_paths: string[]
  tests: string[]
  semantic_terms: string[]
  confidence: number
  confidence_dimensions: ConfidenceDimensions
}

export interface Commit {
  hash: string
  short_hash: string
  timestamp: string
  author: string
  subject: string
  changed_paths: string[]
  additions: number
  deletions: number
  change_type: string
}

export interface TimelineEvent {
  id: string
  capability_id: string
  timestamp: string
  change_type: string
  title: string
  summary: string
  commit_hash: string
  evidence_ids: string[]
}

export interface CapabilityState {
  id: string
  capability_id: string
  kind: string
  timestamp: string
  summary: string
  evidence_ids: string[]
  behavior_ids: string[]
  confidence: number
}

export interface CategorySummary {
  lens_id: string | null
  category: LensLabel
  capability_count: number
  evidence_count: number
}

export interface GraphNode {
  id: string
  label: string
  kind: string
  group: string | null
  metadata: Record<string, unknown>
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: string
  confidence: number
  inferred: boolean
}

export interface GraphProjection {
  label: string
  description: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  truncated: boolean
}

export interface AnalysisResult {
  id: string
  repository: RepositorySummary
  evidence: Evidence[]
  entities: Entity[]
  relationships: unknown[]
  observations: Observation[]
  commits: Commit[]
  behaviors: BehaviorSummary[]
  capabilities: Capability[]
  timeline: TimelineEvent[]
  capability_states: CapabilityState[]
  categories: CategorySummary[]
  lens_set: LensSet | null
  capability_graph: GraphProjection
  code_graph: GraphProjection
  workflow_graph: GraphProjection
  data_graph: GraphProjection
  warnings: string[]
  semantic_mode: string
}
