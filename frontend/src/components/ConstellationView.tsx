import { useMemo } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react'
import { categoryOrder, type CanonicalCategory, type Capability, type GraphProjection } from '../types'

interface ConstellationViewProps {
  activeCategory: CanonicalCategory | 'ALL'
  capabilities: Capability[]
  graph: GraphProjection
  onCategoryChange: (category: CanonicalCategory | 'ALL') => void
  onSelectCapability: (capability: Capability) => void
  query: string
  repositoryName: string
}

const categoryColors: Record<CanonicalCategory, string> = {
  'Product & UX': '#7c5cff',
  'Core Capability': '#15b8c5',
  Data: '#f59e0b',
  'Platform & Integration': '#ec4899',
  'Reliability & Safety': '#438cf5',
  'Quality & Evaluation': '#ef5350',
  Operations: '#20b886',
  'Developer & Documentation': '#7890ae',
}

const maturitySizes: Record<string, number> = {
  DISCOVERED: 18,
  SCAFFOLDED: 22,
  FUNCTIONAL: 27,
  INTEGRATED: 31,
  VALIDATED: 35,
  PRODUCTIONIZED: 39,
}

const ROOT_ID = 'roadtrace:repository'
const MAX_SATELLITES_PER_CATEGORY = 8

export function ConstellationView({
  activeCategory,
  capabilities,
  graph,
  onCategoryChange,
  onSelectCapability,
  query,
  repositoryName,
}: ConstellationViewProps) {
  const capabilityMap = useMemo(
    () => new Map(capabilities.map((capability) => [capability.id, capability])),
    [capabilities],
  )
  const normalizedQuery = query.trim().toLowerCase()
  const matchingCapabilities = capabilities.filter((capability) => {
    if (activeCategory !== 'ALL' && capability.category !== activeCategory) return false
    if (!normalizedQuery) return true
    return `${capability.name} ${capability.description} ${capability.category} ${capability.maturity}`
      .toLowerCase()
      .includes(normalizedQuery)
  })
  const { nodes, edges, hiddenCount } = useMemo(
    () => buildConstellation(repositoryName, matchingCapabilities, activeCategory, Boolean(normalizedQuery)),
    [activeCategory, matchingCapabilities, normalizedQuery, repositoryName],
  )

  return (
    <section className="constellation-card" aria-labelledby="constellation-heading">
      <div className="constellation-card__heading">
        <div>
          <p className="eyebrow">Repository → category → capability</p>
          <h2 id="constellation-heading">Capability constellation</h2>
          <p>Wheel to zoom, drag to pan, and select a capability to inspect its evidence.</p>
        </div>
        <div className="constellation-legend" aria-label="Constellation legend">
          <span><i className="legend-dot legend-dot--repository" /> Repository</span>
          <span><i className="legend-dot legend-dot--category" /> Category</span>
          <span><i className="legend-dot legend-dot--capability" /> Capability size = maturity</span>
        </div>
      </div>
      {matchingCapabilities.length || (!normalizedQuery && graph.nodes.length) ? (
        <>
          <div className="constellation-canvas">
            <ReactFlow
              key={`${activeCategory}:${normalizedQuery}`}
              edges={edges}
              elementsSelectable
              fitView
              fitViewOptions={{ padding: 0.18, maxZoom: 1.25 }}
              maxZoom={2.4}
              minZoom={0.35}
              nodes={nodes}
              nodesConnectable={false}
              nodesDraggable={false}
              onNodeClick={(_event, node) => {
                const capability = capabilityMap.get(node.id)
                if (capability) {
                  onSelectCapability(capability)
                  return
                }
                const nodeCategory = node.data.category
                if (typeof nodeCategory === 'string' && categoryOrder.includes(nodeCategory as CanonicalCategory)) {
                  onCategoryChange(activeCategory === nodeCategory ? 'ALL' : nodeCategory as CanonicalCategory)
                }
              }}
              proOptions={{ hideAttribution: true }}
            >
              <Background className="constellation-grid" color="#20324e" gap={40} size={1} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
          {hiddenCount > 0 && (
            <p className="constellation-note">
              {hiddenCount} additional {hiddenCount === 1 ? 'capability is' : 'capabilities are'} hidden to keep the overview legible.
              Select a category or search to focus it.
            </p>
          )}
        </>
      ) : (
        <div className="graph-empty">
          <span>⌕</span>
          <p>No capability matches the current search and category.</p>
        </div>
      )}
    </section>
  )
}

function buildConstellation(
  repositoryName: string,
  capabilities: Capability[],
  activeCategory: CanonicalCategory | 'ALL',
  searching: boolean,
): { nodes: Node[]; edges: Edge[]; hiddenCount: number } {
  const center = { x: 610, y: 350 }
  const nodes: Node[] = [
    {
      id: ROOT_ID,
      ariaLabel: `${repositoryName} repository`,
      className: 'constellation-node constellation-node--repository',
      data: { label: repositoryName },
      draggable: false,
      position: { x: center.x - 61, y: center.y - 61 },
      selectable: false,
      style: { background: '#edf5ff' },
    },
  ]
  const edges: Edge[] = []
  let hiddenCount = 0

  const grouped = new Map<CanonicalCategory, Capability[]>()
  capabilities.forEach((capability) => {
    const current = grouped.get(capability.category) ?? []
    current.push(capability)
    grouped.set(capability.category, current)
  })

  const visibleCategories = categoryOrder.filter((category) => {
    if (activeCategory !== 'ALL' && category !== activeCategory) return false
    return !searching || (grouped.get(category)?.length ?? 0) > 0
  })

  visibleCategories.forEach((category) => {
    const categoryIndex = categoryOrder.indexOf(category)
    const angle = -Math.PI / 2 + (categoryIndex / categoryOrder.length) * Math.PI * 2
    const categoryCenter = {
      x: center.x + Math.cos(angle) * 405,
      y: center.y + Math.sin(angle) * 245,
    }
    const categoryId = `category:${category}`
    const categoryCapabilities = grouped.get(category) ?? []
    const limit = activeCategory === category || searching ? 30 : MAX_SATELLITES_PER_CATEGORY
    const displayed = categoryCapabilities.slice(0, limit)
    hiddenCount += Math.max(0, categoryCapabilities.length - displayed.length)

    nodes.push({
      id: categoryId,
      ariaLabel: `${category}: ${categoryCapabilities.length} capabilities`,
      className: 'constellation-node constellation-node--category',
      data: {
        category,
        label: (
          <span>
            <strong>{categoryCapabilities.length}</strong>
            <small>{category}</small>
          </span>
        ),
      },
      draggable: false,
      position: { x: categoryCenter.x - 42, y: categoryCenter.y - 42 },
      style: {
        background: categoryColors[category],
        borderColor: lighten(categoryColors[category]),
      },
    })
    edges.push({
      id: `${ROOT_ID}:${categoryId}`,
      source: ROOT_ID,
      target: categoryId,
      className: 'constellation-edge constellation-edge--trunk',
      style: { stroke: categoryColors[category], strokeOpacity: 0.45, strokeWidth: 1.4 },
    })

    displayed.forEach((capability, index) => {
      const ring = Math.floor(index / 8)
      const slot = index % 8
      const slotsInRing = Math.min(8, displayed.length - ring * 8)
      const satelliteAngle = angle - Math.PI * 0.72 + (slot / Math.max(1, slotsInRing - 1)) * Math.PI * 1.44
      const radius = 106 + ring * 61
      const size = maturitySizes[capability.maturity] ?? 22
      nodes.push({
        id: capability.id,
        ariaLabel: `${capability.name}, ${capability.maturity.toLowerCase()}`,
        className: 'constellation-node constellation-node--capability',
        data: {
          category,
          label: (
            <span className="constellation-satellite">
              <span className="constellation-satellite__dot" />
              <span className="constellation-satellite__label">
                <strong>{capability.name}</strong>
                <small>{capability.maturity.toLowerCase()} · {capability.evidence_ids.length} evidence</small>
              </span>
            </span>
          ),
        },
        draggable: false,
        position: {
          x: categoryCenter.x + Math.cos(satelliteAngle) * radius - size / 2,
          y: categoryCenter.y + Math.sin(satelliteAngle) * radius - size / 2,
        },
        style: {
          '--satellite-color': categoryColors[category],
          height: size,
          width: size,
        } as React.CSSProperties,
      })
      edges.push({
        id: `${categoryId}:${capability.id}`,
        source: categoryId,
        target: capability.id,
        className: 'constellation-edge',
        style: { stroke: categoryColors[category], strokeOpacity: 0.34, strokeWidth: 1 },
      })
    })
  })

  return { nodes, edges, hiddenCount }
}

function lighten(color: string): string {
  return `${color}cc`
}
