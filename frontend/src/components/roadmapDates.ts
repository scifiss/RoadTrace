import type { RepositorySummary } from '../types'

export interface RoadmapDateRange {
  start: string
  end: string
}

export function repositoryHistoryRange(
  repository: Pick<RepositorySummary, 'history_start' | 'history_end'>,
  fallbackTimestamps: string[] = [],
): RoadmapDateRange {
  const validFallbacks = fallbackTimestamps
    .map((timestamp) => ({ date: new Date(timestamp), value: dateInputValue(timestamp) }))
    .filter((item) => item.value && !Number.isNaN(item.date.getTime()))
    .sort((left, right) => left.date.getTime() - right.date.getTime())

  return {
    start: dateInputValue(repository.history_start) || validFallbacks[0]?.value || '',
    end: dateInputValue(repository.history_end) || validFallbacks.at(-1)?.value || '',
  }
}

export function roadmapDateBounds(
  start: string,
  end: string,
  fallback: RoadmapDateRange,
): { min: Date; max: Date } {
  const fallbackStart = parseDate(fallback.start) ?? new Date()
  const min = parseDate(start) ?? fallbackStart
  const requestedMax = parseDate(end) ?? parseDate(fallback.end) ?? new Date(min.getTime() + 86_400_000)
  return {
    min,
    max: new Date(Math.max(requestedMax.getTime(), min.getTime() + 86_400_000)),
  }
}

function dateInputValue(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : value.slice(0, 10)
}

function parseDate(value: string): Date | null {
  if (!value) return null
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(date.getTime()) ? null : date
}
