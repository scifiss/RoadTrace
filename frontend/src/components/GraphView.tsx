import { useMemo, useState } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  MarkerType,
  type Edge,
  type Node,
} from '@xyflow/react'
import type { Capability, GraphNode, GraphProjection } from '../types'
import { matchesGraphNode, selectGraphProjection } from './graphProjection'

interface GraphViewProps {
  graph: GraphProjection
  capabilities: Capability[]
  onSelectCapability: (capability: Capability) => void
  query: string
}

export function GraphView({ graph, capabilities, onSelectCapability, query }: GraphViewProps) {
  const firstEntry = useMemo(() => findFirstEntry(graph), [graph])
  const [focusId, setFocusId] = useState<string | null>(
    graph.label === 'Inferred workflows' ? firstEntry?.id ?? null : null,
  )
  const [depth, setDepth] = useState(1)
  const [showFull, setShowFull] = useState(false)
  const capabilityMap = useMemo(
    () => new Map(capabilities.map((capability) => [capability.id, capability])),
    [capabilities],
  )
  const visibleGraph = useMemo(
    () => selectGraphProjection(graph, { depth, focusId: query ? null : focusId, query, showFull }),
    [depth, focusId, graph, query, showFull],
  )
  const visibleFocusId = focusId && visibleGraph.nodes.some((node) => node.id === focusId)
    ? focusId
    : null
  const flowNodes = useMemo<Node[]>(
    () => layoutNodes(visibleGraph, visibleFocusId),
    [visibleFocusId, visibleGraph],
  )
  const flowEdges = useMemo<Edge[]>(
    () =>
      visibleGraph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: visibleGraph.edges.length <= 18 ? edge.type.toLowerCase().replaceAll('_', ' ') : undefined,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        animated: edge.inferred,
        style: {
          stroke: edge.inferred ? '#e3aa45' : '#7890ae',
          strokeWidth: Math.max(1, edge.confidence * 1.8),
          strokeDasharray: edge.inferred ? '5 5' : undefined,
        },
        labelStyle: { fontSize: 10, fill: '#aebdd2' },
        labelBgStyle: { fill: '#0c192b', fillOpacity: 0.92 },
      })),
    [visibleGraph],
  )
  const focusNode = graph.nodes.find((node) => node.id === focusId)
  const options = [...graph.nodes]
    .filter((node) => matchesGraphNode(node, query))
    .sort(compareGraphNodes)
    .slice(0, 100)

  return (
    <section className="graph-card" aria-label={graph.label}>
      <div className="graph-card__heading">
        <div>
          <p className="eyebrow">Focused interactive projection</p>
          <h2>{graph.label}</h2>
        </div>
        <p>
          {graph.description} Select a node to trace its immediate neighborhood.
          {graph.truncated && <span className="bounded-label">Bounded source</span>}
        </p>
      </div>
      <div className="graph-toolbar">
        <label>
          <span>Focus node</span>
          <select
            onChange={(event) => {
              setFocusId(event.target.value || null)
              setShowFull(false)
            }}
            value={focusId && options.some((node) => node.id === focusId) ? focusId : ''}
          >
            <option value="">Overview</option>
            {options.map((node) => (
              <option key={node.id} value={node.id}>
                {node.label} · {nodeContext(node)} · {formatKind(node.kind)}
              </option>
            ))}
          </select>
        </label>
        {focusNode && (
          <div className="graph-depth" aria-label="Neighborhood depth">
            <span>Trace depth</span>
            <button aria-pressed={depth === 1} onClick={() => setDepth(1)} type="button">1 hop</button>
            <button aria-pressed={depth === 2} onClick={() => setDepth(2)} type="button">2 hops</button>
          </div>
        )}
        <div className="graph-toolbar__status">
          <strong>{visibleGraph.nodes.length}</strong> of {graph.nodes.length} nodes
        </div>
        {(showFull || visibleGraph.nodes.length < graph.nodes.length) && (
          <button
            className="graph-show-all"
            onClick={() => {
              setShowFull((current) => !current)
              if (!showFull) setFocusId(null)
            }}
            type="button"
          >
            {showFull ? 'Return to overview' : 'Show full bounded graph'}
          </button>
        )}
      </div>
      {flowNodes.length ? (
        <div className="graph-canvas">
          <ReactFlow
            key={`${focusId ?? 'overview'}:${depth}:${showFull}:${query}`}
            fitView
            fitViewOptions={{ padding: 0.24, maxZoom: 1.15 }}
            nodes={flowNodes}
            edges={flowEdges}
            minZoom={0.3}
            maxZoom={1.8}
            nodesDraggable
            nodesConnectable={false}
            onNodeClick={(_event, node) => {
              const capability = capabilityMap.get(node.id)
              if (capability) onSelectCapability(capability)
              setFocusId(node.id)
              setShowFull(false)
            }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#20324e" gap={28} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      ) : (
        <div className="graph-empty">
          <span>⌕</span>
          <p>No nodes match the current search.</p>
        </div>
      )}
    </section>
  )
}

function findFirstEntry(graph: GraphProjection): GraphNode | undefined {
  const explicit = graph.nodes.find((node) => node.metadata.entrypoint === true)
  if (explicit) return explicit
  const targets = new Set(graph.edges.map((edge) => edge.target))
  return graph.nodes.find((node) => !targets.has(node.id)) ?? graph.nodes[0]
}

function layoutNodes(graph: GraphProjection, focusId: string | null): Node[] {
  const layers = focusId ? assignLayers(graph, focusId) : null
  const layerRows = new Map<number, number>()
  const minLayer = layers ? Math.min(...layers.values()) : 0

  return graph.nodes.map((item, index) => {
    const layer = layers?.get(item.id) ?? 0
    const row = layers ? layerRows.get(layer) ?? 0 : Math.floor(index / 5)
    if (layers) layerRows.set(layer, row + 1)
    const position = layers
      ? { x: (layer - minLayer) * 265, y: row * 92 }
      : { x: (index % 5) * 245, y: Math.floor(index / 5) * 92 }
    return {
      id: item.id,
      ariaLabel: `${item.label}, ${nodeContext(item)}, ${formatKind(item.kind)}`,
      position,
      data: {
        label: (
          <span className="flow-node__label">
            <strong>{item.label}</strong>
            <small title={String(item.metadata.file_path ?? item.group ?? '')}>
              {nodeContext(item)}
            </small>
            <em>{formatKind(item.kind)}</em>
          </span>
        ),
      },
      className: `flow-node flow-node--${item.kind.toLowerCase()}${item.id === focusId ? ' flow-node--focused' : ''}`,
      style: {
        background: nodeColor(item.kind),
        borderColor: nodeBorder(item.kind),
      },
    }
  })
}

function nodeContext(node: GraphNode): string {
  const path = String(node.metadata.file_path ?? node.group ?? '')
  const compactPath = path.split('/').filter(Boolean).slice(-2).join('/') || 'project structure'
  const line = Number(node.metadata.line)
  return Number.isFinite(line) && line > 0 ? `${compactPath}:${line}` : compactPath
}

function compareGraphNodes(left: GraphNode, right: GraphNode): number {
  const kindOrder = [
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
  const leftKind = kindOrder.indexOf(left.kind)
  const rightKind = kindOrder.indexOf(right.kind)
  const kindDifference = (leftKind < 0 ? kindOrder.length : leftKind)
    - (rightKind < 0 ? kindOrder.length : rightKind)
  if (kindDifference) return kindDifference
  return left.label.localeCompare(right.label) || nodeContext(left).localeCompare(nodeContext(right))
}

function assignLayers(graph: GraphProjection, focusId: string): Map<string, number> {
  const layers = new Map<string, number>([[focusId, 0]])
  const queue = [focusId]
  while (queue.length) {
    const id = queue.shift()!
    const layer = layers.get(id) ?? 0
    graph.edges.forEach((edge) => {
      if (edge.source === id && !layers.has(edge.target)) {
        layers.set(edge.target, layer + 1)
        queue.push(edge.target)
      } else if (edge.target === id && !layers.has(edge.source)) {
        layers.set(edge.source, layer - 1)
        queue.push(edge.source)
      }
    })
  }
  graph.nodes.forEach((node) => {
    if (!layers.has(node.id)) layers.set(node.id, Math.max(...layers.values()) + 1)
  })
  return layers
}

function formatKind(kind: string): string {
  return kind.toLowerCase().replaceAll('_', ' ')
}

function nodeColor(kind: string): string {
  if (kind.includes('API')) return '#44243a'
  if (kind.includes('SCHEMA')) return '#183b3d'
  if (kind.includes('UI')) return '#302752'
  if (kind.includes('TEST')) return '#344024'
  if (kind.includes('EXTERNAL')) return '#1d344e'
  return '#122138'
}

function nodeBorder(kind: string): string {
  if (kind.includes('API')) return '#ed6f91'
  if (kind.includes('SCHEMA')) return '#32c6ad'
  if (kind.includes('UI')) return '#9a7cff'
  if (kind.includes('TEST')) return '#a8bd4d'
  return '#607a9e'
}
