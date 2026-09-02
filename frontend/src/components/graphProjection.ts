import type { GraphNode, GraphProjection } from '../types'

const OVERVIEW_NODE_LIMIT = 30
const SEARCH_NODE_LIMIT = 42

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
    selectedIds = new Set(graph.nodes.slice(0, OVERVIEW_NODE_LIMIT).map((node) => node.id))
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
