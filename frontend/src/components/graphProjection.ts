import type { GraphNode, GraphProjection } from '../types'

const OVERVIEW_NODE_LIMIT = 24
const SEARCH_NODE_LIMIT = 42

const OVERVIEW_KIND_ORDER = [
  'API_ENDPOINT',
  'UI_COMPONENT',
  'SCHEMA',
  'CLASS',
  'MODULE',
  'CONFIGURATION',
  'FUNCTION',
  'TEST',
  'METHOD',
  'EXTERNAL_MODULE',
  'FILE',
]

interface SelectionOptions {
  depth: number
  focusId: string | null
  query: string
  showFull: boolean
}

export function selectGraphProjection(
  graph: GraphProjection,
  { depth, focusId, query, showFull }: SelectionOptions,
): GraphProjection {
  if (showFull) return graph

  const normalizedQuery = query.trim().toLowerCase()
  let selectedIds: Set<string>
  if (focusId && graph.nodes.some((node) => node.id === focusId)) {
    selectedIds = neighborhoodIds(graph, [focusId], depth)
  } else if (normalizedQuery) {
    const matches = graph.nodes.filter((node) => matchesGraphNode(node, normalizedQuery)).slice(0, 14)
    selectedIds = neighborhoodIds(graph, matches.map((node) => node.id), 1)
  } else {
    selectedIds = representativeOverviewIds(graph)
  }

  const limit = normalizedQuery ? SEARCH_NODE_LIMIT : OVERVIEW_NODE_LIMIT
  const selectedNodes = graph.nodes.filter((node) => selectedIds.has(node.id)).slice(0, limit)
  const boundedIds = new Set(selectedNodes.map((node) => node.id))
  const selectedEdges = graph.edges.filter(
    (edge) => boundedIds.has(edge.source) && boundedIds.has(edge.target),
  )
  return {
    ...graph,
    nodes: selectedNodes,
    edges: selectedEdges,
    truncated: graph.truncated || selectedNodes.length < graph.nodes.length,
  }
}

function representativeOverviewIds(graph: GraphProjection): Set<string> {
  const degree = new Map<string, number>()
  graph.edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1)
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1)
  })
  const kinds = [
    ...OVERVIEW_KIND_ORDER,
    ...new Set(
      graph.nodes
        .map((node) => node.kind)
        .filter((kind) => !OVERVIEW_KIND_ORDER.includes(kind)),
    ),
  ]
  const buckets = new Map(
    kinds.map((kind) => [
      kind,
      graph.nodes
        .filter((node) => node.kind === kind)
        .sort((left, right) => {
          const degreeDifference = (degree.get(right.id) ?? 0) - (degree.get(left.id) ?? 0)
          if (degreeDifference) return degreeDifference
          const entryDifference = Number(right.metadata.entrypoint === true)
            - Number(left.metadata.entrypoint === true)
          return entryDifference || left.label.localeCompare(right.label)
        }),
    ]),
  )
  const cursors = new Map(kinds.map((kind) => [kind, 0]))
  const labelCounts = new Map<string, number>()
  const groupCounts = new Map<string, number>()
  const selected = new Set<string>()

  while (selected.size < OVERVIEW_NODE_LIMIT) {
    let progressed = false
    kinds.forEach((kind) => {
      if (selected.size >= OVERVIEW_NODE_LIMIT) return
      const bucket = buckets.get(kind) ?? []
      let cursor = cursors.get(kind) ?? 0
      while (cursor < bucket.length) {
        const node = bucket[cursor]
        cursor += 1
        const labelKey = node.label.trim().toLowerCase()
        const groupKey = node.group ?? String(node.metadata.file_path ?? '')
        if ((labelCounts.get(labelKey) ?? 0) >= 2) continue
        if (groupKey && (groupCounts.get(groupKey) ?? 0) >= 3) continue
        selected.add(node.id)
        labelCounts.set(labelKey, (labelCounts.get(labelKey) ?? 0) + 1)
        if (groupKey) groupCounts.set(groupKey, (groupCounts.get(groupKey) ?? 0) + 1)
        progressed = true
        break
      }
      cursors.set(kind, cursor)
    })
    if (!progressed) break
  }
  return selected
}

export function matchesGraphNode(node: GraphNode, query: string): boolean {
  const normalizedQuery = query.trim().toLowerCase()
  if (!normalizedQuery) return true
  return `${node.label} ${node.kind} ${node.group ?? ''} ${String(node.metadata.file_path ?? '')}`
    .toLowerCase()
    .includes(normalizedQuery)
}

function neighborhoodIds(graph: GraphProjection, seeds: string[], depth: number): Set<string> {
  const selected = new Set(seeds)
  let frontier = new Set(seeds)
  for (let level = 0; level < depth; level += 1) {
    const next = new Set<string>()
    graph.edges.forEach((edge) => {
      if (frontier.has(edge.source) && !selected.has(edge.target)) next.add(edge.target)
      if (frontier.has(edge.target) && !selected.has(edge.source)) next.add(edge.source)
    })
    next.forEach((id) => selected.add(id))
    frontier = next
    if (!frontier.size) break
  }
  return selected
}
