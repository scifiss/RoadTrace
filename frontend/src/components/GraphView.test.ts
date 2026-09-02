import { describe, expect, it } from 'vitest'
import type { GraphProjection } from '../types'
import { selectGraphProjection } from './graphProjection'

const graph: GraphProjection = {
  label: 'Code graph',
  description: 'Test projection',
  nodes: [
    { id: 'api', label: 'create_route', kind: 'API_ENDPOINT', group: 'api.py', metadata: {} },
    { id: 'service', label: 'RouteService', kind: 'CLASS', group: 'service.py', metadata: {} },
    { id: 'store', label: 'RouteStore', kind: 'SCHEMA', group: 'store.py', metadata: {} },
    { id: 'docs', label: 'Guide', kind: 'FILE', group: 'README.md', metadata: {} },
  ],
  edges: [
    { id: 'api-service', source: 'api', target: 'service', type: 'CALLS', confidence: 1, inferred: false },
    { id: 'service-store', source: 'service', target: 'store', type: 'INSTANTIATES', confidence: 1, inferred: false },
  ],
  truncated: false,
}

describe('focused graph selection', () => {
  it('shows only the immediate neighborhood at one hop', () => {
    const selected = selectGraphProjection(graph, {
      depth: 1,
      focusId: 'service',
      query: '',
      showFull: false,
    })

    expect(selected.nodes.map((node) => node.id)).toEqual(['api', 'service', 'store'])
    expect(selected.nodes).toHaveLength(3)
    expect(selected.truncated).toBe(true)
  })

  it('searches labels and file paths while retaining context', () => {
    const selected = selectGraphProjection(graph, {
      depth: 1,
      focusId: null,
      query: 'store.py',
      showFull: false,
    })

    expect(selected.nodes.map((node) => node.id)).toEqual(['service', 'store'])
    expect(selected.edges.map((edge) => edge.id)).toEqual(['service-store'])
  })

  it('keeps the full bounded projection behind an explicit control', () => {
    const selected = selectGraphProjection(graph, {
      depth: 1,
      focusId: 'service',
      query: '',
      showFull: true,
    })

    expect(selected).toBe(graph)
  })
})
