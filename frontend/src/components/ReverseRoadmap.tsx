import { useEffect, useMemo, useState } from 'react'
import type { AnalysisResult, CanonicalCategory, Capability, TimelineEvent } from '../types'
import { repositoryHistoryRange, roadmapDateBounds } from './roadmapDates'

interface ReverseRoadmapProps {
  category: CanonicalCategory | 'ALL'
  query: string
  result: AnalysisResult
  onSelectCapability: (capability: Capability) => void
}

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
  const events = result.timeline.filter((event) => {
    const capability = capabilityMap.get(event.capability_id)
    if (!capability) return false
    if (category !== 'ALL' && capability.category !== category) return false
    if (capabilityId !== 'ALL' && event.capability_id !== capabilityId) return false
    const normalizedQuery = query.trim().toLowerCase()
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
  const lanes = new Map<string, number>()
  events.forEach((event) => {
    if (!lanes.has(event.capability_id)) lanes.set(event.capability_id, lanes.size)
  })
  const height = Math.max(300, lanes.size * 88 + 90)

  return (
    <section className="section-block" aria-labelledby="roadmap-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Code history → capability evolution</p>
          <h2 id="roadmap-heading">Reverse roadmap</h2>
        </div>
        <p>Appearance is estimated from the earliest bounded commit that touched supporting code.</p>
      </div>
      <div className="timeline-filters timeline-filters--compact" aria-label="Roadmap filters">
        <label>
          <span>Capability</span>
          <select value={capabilityId} onChange={(event) => setCapabilityId(event.target.value)}>
            <option value="ALL">All capabilities</option>
            {visibleCapabilities.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
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
      </div>
      {events.length ? (
        <div className="timeline-scroll">
          <div className="timeline" style={{ height }}>
            <div className="timeline-axis">
              <span>{formatMonth(dateBounds.min)}</span>
              <span>{formatMonth(new Date((dateBounds.min.getTime() + dateBounds.max.getTime()) / 2))}</span>
              <span>{formatMonth(dateBounds.max)}</span>
            </div>
            {[...lanes.entries()].map(([id, lane]) => (
              <div className="timeline-lane" key={id} style={{ top: lane * 88 + 55 }}>
                <span>{capabilityMap.get(id)?.name}</span>
              </div>
            ))}
            {events.map((event) => {
              const capability = capabilityMap.get(event.capability_id)!
              const left = eventPosition(event, dateBounds.min, dateBounds.max)
              const lane = lanes.get(event.capability_id) ?? 0
              return (
                <button
                  className={`timeline-event timeline-event--${event.change_type.toLowerCase()}`}
                  key={event.id}
                  onClick={() => onSelectCapability(capability)}
                  style={{ left: `${left}%`, top: lane * 88 + 75 }}
                  type="button"
                >
                  <span>{event.change_type === 'NEW_CAPABILITY' ? '◆' : '●'}</span>
                  <div>
                    <strong>{event.title}</strong>
                    <small>{formatMonth(new Date(event.timestamp))} · {event.commit_hash.slice(0, 8)}</small>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="timeline-empty">
          <span>—</span>
          <p>No timeline events match these filters.</p>
        </div>
      )}
    </section>
  )
}

function eventPosition(event: TimelineEvent, min: Date, max: Date): number {
  const range = max.getTime() - min.getTime()
  return 8 + ((new Date(event.timestamp).getTime() - min.getTime()) / range) * 84
}

function formatMonth(date: Date): string {
  return new Intl.DateTimeFormat('en', { month: 'short', year: 'numeric' }).format(date)
}
