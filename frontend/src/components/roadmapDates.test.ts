import { describe, expect, it } from 'vitest'
import {
  formatRoadmapTick,
  repositoryHistoryRange,
  roadmapDateBounds,
  roadmapTimeTicks,
} from './roadmapDates'

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

  it('creates readable ticks across short and long histories', () => {
    const shortMin = new Date('2026-08-11T00:00:00Z')
    const shortMax = new Date('2026-09-01T00:00:00Z')
    const shortTicks = roadmapTimeTicks(shortMin, shortMax, 5)
    expect(shortTicks).toHaveLength(5)
    expect(formatRoadmapTick(shortTicks[0], shortMin, shortMax)).toBe('Aug 11')
    expect(formatRoadmapTick(shortTicks.at(-1)!, shortMin, shortMax)).toBe('Sep 1')

    const longMin = new Date('2021-01-01T00:00:00Z')
    const longMax = new Date('2026-01-01T00:00:00Z')
    expect(formatRoadmapTick(longMin, longMin, longMax)).toBe('2021')
  })
})
