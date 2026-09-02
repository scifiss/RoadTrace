export const categoryOrder = [
  'Product & UX',
  'Core Capability',
  'Data',
  'Platform & Integration',
  'Reliability & Safety',
  'Quality & Evaluation',
  'Operations',
  'Developer & Documentation',
] as const

export type CanonicalCategory = (typeof categoryOrder)[number]

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
  category: CanonicalCategory
  parent_id: string | null
  child_ids: string[]
  entity_ids: string[]
  evidence_ids: string[]
  commit_hashes: string[]
  first_seen: string | null
  last_changed: string | null
  maturity: string
  maturity_signals: MaturitySignals
  confidence: number
  reasoning_summary: string
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

export interface CategorySummary {
  category: CanonicalCategory
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
  commits: Commit[]
  capabilities: Capability[]
  timeline: TimelineEvent[]
  categories: CategorySummary[]
  capability_graph: GraphProjection
  code_graph: GraphProjection
  workflow_graph: GraphProjection
  data_graph: GraphProjection
  warnings: string[]
  semantic_mode: string
}
