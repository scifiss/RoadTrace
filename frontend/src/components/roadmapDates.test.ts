import { describe, expect, it } from 'vitest'
import { repositoryHistoryRange, roadmapDateBounds } from './roadmapDates'

describe('reverse-roadmap history range', () => {
  it('defaults to the complete observed repository history', () => {
    const range = repositoryHistoryRange({
      history_start: '2022-03-14T09:12:00Z',
      history_end: '2026-09-02T18:30:00Z',
    })

    expect(range).toEqual({ start: '2022-03-14', end: '2026-09-02' })
    const bounds = roadmapDateBounds(range.start, range.end, range)
    expect(bounds.min.toISOString()).toBe('2022-03-14T00:00:00.000Z')
    expect(bounds.max.toISOString()).toBe('2026-09-02T00:00:00.000Z')
  })

  it('falls back to the first and last timeline events when Git bounds are absent', () => {
    const range = repositoryHistoryRange(
      { history_start: null, history_end: null },
      ['2025-06-12T00:00:00Z', '2024-01-04T00:00:00Z'],
    )

    expect(range).toEqual({ start: '2024-01-04', end: '2025-06-12' })
  })
})
