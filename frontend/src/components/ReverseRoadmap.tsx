import { useEffect, useMemo, useState } from 'react'
import type {
  AnalysisResult,
  CanonicalCategory,
  Capability,
  Commit,
  TimelineEvent,
} from '../types'
import {
  formatRoadmapTick,
  repositoryHistoryRange,
  roadmapDateBounds,
  roadmapTimeTicks,
} from './roadmapDates'

interface ReverseRoadmapProps {
  category: CanonicalCategory | 'ALL'
  query: string
  result: AnalysisResult
  onSelectCapability: (capability: Capability) => void
}

const ACTIVITY_BIN_COUNT = 36

export function ReverseRoadmap({ category, query, result, onSelectCapability }: ReverseRoadmapProps) {
  const historyRange = useMemo(
    () => repositoryHistoryRange(result.repository, result.timeline.map((event) => event.timestamp)),
    [result.repository, result.timeline],
  )
  const [capabilityId, setCapabilityId] = useState('ALL')
  const [start, setStart] = useState(historyRange.start)
  const [end, setEnd] = useState(historyRange.end)
  const capabilityMap = useMemo(
    () => new Map(result.capabilities.map((item) => [item.id, item])),
    [result.capabilities],
  )
  const visibleCapabilities = result.capabilities.filter(
    (item) => category === 'ALL' || item.category === category,
  )

  useEffect(() => {
    if (capabilityId !== 'ALL' && !visibleCapabilities.some((item) => item.id === capabilityId)) {
      setCapabilityId('ALL')
    }
  }, [capabilityId, visibleCapabilities])

  const normalizedQuery = query.trim().toLowerCase()
  const events = result.timeline.filter((event) => {
    const capability = capabilityMap.get(event.capability_id)
    if (!capability) return false
    if (category !== 'ALL' && capability.category !== category) return false
    if (capabilityId !== 'ALL' && event.capability_id !== capabilityId) return false
    if (
      normalizedQuery &&
      !`${capability.name} ${capability.description} ${event.title} ${event.summary}`
        .toLowerCase()
        .includes(normalizedQuery)
    ) return false
    const day = event.timestamp.slice(0, 10)
    return (!start || day >= start) && (!end || day <= end)
  })
  const dateBounds = roadmapDateBounds(start, end, historyRange)
  const ticks = roadmapTimeTicks(dateBounds.min, dateBounds.max)
  const eventsByCapability = new Map<string, TimelineEvent[]>()
  events.forEach((event) => {
    const current = eventsByCapability.get(event.capability_id) ?? []
    current.push(event)
    eventsByCapability.set(event.capability_id, current)
  })
  const rows = visibleCapabilities.filter((capability) => eventsByCapability.has(capability.id))
  const activity = buildActivityBins(result.commits, dateBounds.min, dateBounds.max)
  const visibleCommitCount = activity.reduce((total, bin) => total + bin.count, 0)
  const fullHistorySelected = start === historyRange.start && end === historyRange.end

  return (
    <section className="section-block roadmap-section" aria-labelledby="roadmap-heading">
      <div className="section-heading roadmap-heading">
        <div>
          <p className="eyebrow">Code history → capability evolution</p>
          <h2 id="roadmap-heading">Reverse roadmap</h2>
        </div>
        <p>
          A repository-wide overview of when capabilities first appeared and how later commits
          strengthened them. Every milestone opens its supporting evidence.
        </p>
      </div>

      <div className="timeline-filters" aria-label="Roadmap filters">
        <label>
          <span>Capability</span>
          <select value={capabilityId} onChange={(event) => setCapabilityId(event.target.value)}>
            <option value="ALL">All capabilities</option>
            {visibleCapabilities.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>From</span>
          <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
        </label>
        <label>
          <span>To</span>
          <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
        </label>
        <button
          className="timeline-range-reset"
          disabled={fullHistorySelected}
          onClick={() => {
            setStart(historyRange.start)
            setEnd(historyRange.end)
          }}
          type="button"
        >
          <span>Range</span>
          Whole observed history
        </button>
      </div>

      <div className="roadmap-meta">
        <p>
          <strong>{rows.length}</strong> {rows.length === 1 ? 'capability' : 'capabilities'} ·{' '}
          <strong>{events.length}</strong> evidence {events.length === 1 ? 'milestone' : 'milestones'} ·{' '}
          {formatRange(dateBounds.min, dateBounds.max)}
        </p>
        <div className="timeline-legend" aria-label="Roadmap event legend">
          <Legend tone="origin" label="First observed" diamond />
          <Legend tone="feature" label="Feature evolution" />
          <Legend tone="quality" label="Quality & tests" />
          <Legend tone="fix" label="Fix or removal" />
          <Legend tone="operations" label="Operations & docs" />
        </div>
      </div>

      {rows.length ? (
        <div className="timeline-scroll">
          <div className="timeline-table">
            <div className="timeline-axis-row">
              <div className="timeline-axis-title">
                <strong>Capability</strong>
                <span>Evidence-backed milestones</span>
              </div>
              <TimelineAxis ticks={ticks} min={dateBounds.min} max={dateBounds.max} />
            </div>

            <div className="timeline-activity-row">
              <div className="timeline-row-label timeline-row-label--activity">
                <strong>Commit activity</strong>
                <span>{visibleCommitCount} sampled commits in range</span>
              </div>
              <div className="timeline-activity-track">
                <TickGrid ticks={ticks} min={dateBounds.min} max={dateBounds.max} />
                {activity.map((bin, index) => (
                  <span
                    aria-label={`${bin.count} commits in this period`}
                    className="timeline-activity-bar"
                    key={index}
                    style={{ height: bin.count ? `${Math.max(12, bin.intensity * 100)}%` : 0 }}
                    title={`${bin.count} commits`}
                  />
                ))}
              </div>
            </div>

            {rows.map((capability) => {
              const capabilityEvents = eventsByCapability.get(capability.id) ?? []
              const firstPosition = eventPosition(capabilityEvents[0], dateBounds.min, dateBounds.max)
              const lastPosition = eventPosition(
                capabilityEvents.at(-1) ?? capabilityEvents[0],
                dateBounds.min,
                dateBounds.max,
              )
              return (
                <div className="timeline-row" key={capability.id}>
                  <button
                    className="timeline-row-label"
                    onClick={() => onSelectCapability(capability)}
                    type="button"
                  >
                    <strong>{capability.name}</strong>
                    <span>{capability.category} · {capability.maturity.toLowerCase()}</span>
                  </button>
                  <div className="timeline-track">
                    <TickGrid ticks={ticks} min={dateBounds.min} max={dateBounds.max} />
                    <span
                      className="timeline-evolution-line"
                      style={{ left: `${firstPosition}%`, width: `${Math.max(0.35, lastPosition - firstPosition)}%` }}
                    />
                    {capabilityEvents.map((event) => (
                      <TimelineMarker
                        capability={capability}
                        event={event}
                        key={event.id}
                        left={eventPosition(event, dateBounds.min, dateBounds.max)}
                        onSelect={onSelectCapability}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="timeline-empty">
          <span>—</span>
          <p>No evidence milestones match these filters.</p>
        </div>
      )}
    </section>
  )
}

function TimelineAxis({ ticks, min, max }: { ticks: Date[]; min: Date; max: Date }) {
  return (
    <div className="timeline-axis-track">
      {ticks.map((tick, index) => (
        <span
          className="timeline-axis-tick"
          data-edge={index === 0 ? 'start' : index === ticks.length - 1 ? 'end' : undefined}
          key={tick.toISOString()}
          style={{ left: `${datePosition(tick, min, max)}%` }}
        >
          {formatRoadmapTick(tick, min, max)}
        </span>
      ))}
    </div>
  )
}

function TickGrid({ ticks, min, max }: { ticks: Date[]; min: Date; max: Date }) {
  return (
    <>
      {ticks.map((tick) => (
        <span
          aria-hidden="true"
          className="timeline-gridline"
          key={tick.toISOString()}
          style={{ left: `${datePosition(tick, min, max)}%` }}
        />
      ))}
    </>
  )
}

function TimelineMarker({
  capability,
  event,
  left,
  onSelect,
}: {
  capability: Capability
  event: TimelineEvent
  left: number
  onSelect: (capability: Capability) => void
}) {
  const visual = eventVisual(event.change_type)
  return (
    <button
      aria-label={`${event.title}, ${formatEventDate(event.timestamp)}`}
      className={`timeline-marker timeline-marker--${visual.tone}${visual.diamond ? ' timeline-marker--diamond' : ''}`}
      onClick={() => onSelect(capability)}
      style={{ left: `${left}%` }}
      title={`${event.title} — ${formatEventDate(event.timestamp)} — ${event.summary}`}
      type="button"
    >
      <span className="timeline-tooltip">
        <strong>{event.title}</strong>
        <small>{formatEventDate(event.timestamp)} · {event.commit_hash.slice(0, 8)}</small>
        <em>{event.summary}</em>
      </span>
    </button>
  )
}

function Legend({
  diamond = false,
  label,
  tone,
}: {
  diamond?: boolean
  label: string
  tone: string
}) {
  return (
    <span>
      <i className={`timeline-legend-mark timeline-marker--${tone}${diamond ? ' timeline-marker--diamond' : ''}`} />
      {label}
    </span>
  )
}

function eventVisual(changeType: string): { tone: string; diamond: boolean } {
  if (changeType === 'NEW_CAPABILITY') return { tone: 'origin', diamond: true }
  if (changeType === 'TEST_MATURATION') return { tone: 'quality', diamond: false }
  if (['BUG_FIX', 'REMOVAL'].includes(changeType)) return { tone: 'fix', diamond: false }
  if (['OPERATIONS', 'DOCUMENTATION', 'MIGRATION'].includes(changeType)) {
    return { tone: 'operations', diamond: false }
  }
  return { tone: 'feature', diamond: false }
}

function buildActivityBins(
  commits: Commit[],
  min: Date,
  max: Date,
): { count: number; intensity: number }[] {
  const counts = Array.from({ length: ACTIVITY_BIN_COUNT }, () => 0)
  const range = Math.max(1, max.getTime() - min.getTime())
  commits.forEach((commit) => {
    const timestamp = new Date(commit.timestamp).getTime()
    if (timestamp < min.getTime() || timestamp > max.getTime()) return
    const index = Math.min(
      ACTIVITY_BIN_COUNT - 1,
      Math.floor(((timestamp - min.getTime()) / range) * ACTIVITY_BIN_COUNT),
    )
    counts[index] += 1
  })
  const maximum = Math.max(1, ...counts)
  return counts.map((count) => ({ count, intensity: count / maximum }))
}

function eventPosition(event: TimelineEvent, min: Date, max: Date): number {
  return Math.min(99.4, Math.max(0.6, datePosition(new Date(event.timestamp), min, max)))
}

function datePosition(date: Date, min: Date, max: Date): number {
  const range = Math.max(1, max.getTime() - min.getTime())
  return ((date.getTime() - min.getTime()) / range) * 100
}

function formatRange(min: Date, max: Date): string {
  const formatter = new Intl.DateTimeFormat('en', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
    year: 'numeric',
  })
  return `${formatter.format(min)} – ${formatter.format(max)}`
}

function formatEventDate(value: string): string {
  return new Intl.DateTimeFormat('en', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
    year: 'numeric',
  }).format(new Date(value))
}
