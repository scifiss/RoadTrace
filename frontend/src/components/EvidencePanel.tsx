import { useMemo } from 'react'
import type { AnalysisResult, Capability, Evidence } from '../types'

interface EvidencePanelProps {
  capability: Capability | null
  result: AnalysisResult
  onClose: () => void
}

function EvidenceRow({ evidence }: { evidence: Evidence }) {
  const location = evidence.file_path
    ? `${evidence.file_path}${evidence.line_start ? `:${evidence.line_start}` : ''}`
    : evidence.commit_hash?.slice(0, 8)
  return (
    <li className="evidence-row">
      <span className={`evidence-kind evidence-kind--${evidence.kind.toLowerCase()}`}>
        {evidence.kind.replace('_', ' ')}
      </span>
      <div>
        <strong>{evidence.label}</strong>
        {location && <code>{location}</code>}
        {evidence.detail && <p>{evidence.detail}</p>}
      </div>
    </li>
  )
}

export function EvidencePanel({ capability, result, onClose }: EvidencePanelProps) {
  const grouped = useMemo(() => {
    if (!capability) return { code: [], history: [], quality: [] }
    const selected = new Set(capability.evidence_ids)
    const items = result.evidence.filter((item) => selected.has(item.id))
    return {
      code: items.filter((item) => !['COMMIT', 'TEST', 'DOCUMENTATION'].includes(item.kind)),
      history: items.filter((item) => item.kind === 'COMMIT'),
      quality: items.filter((item) => ['TEST', 'DOCUMENTATION'].includes(item.kind)),
    }
  }, [capability, result.evidence])

  if (!capability) return null
  const signalEntries = Object.entries(capability.maturity_signals)
  return (
    <aside aria-labelledby="evidence-title" className="evidence-panel">
      <div className="evidence-panel__header">
        <div>
          <p className="eyebrow">Why RoadTrace believes this exists</p>
          <h2 id="evidence-title">{capability.name}</h2>
        </div>
        <button aria-label="Close evidence panel" className="icon-button" onClick={onClose} type="button">
          ×
        </button>
      </div>
      <p className="evidence-description">{capability.description}</p>
      <div className="inference-callout">
        <span>Inference</span>
        <p>{capability.reasoning_summary}</p>
      </div>
      <div className="evidence-metrics">
        <div>
          <span>Maturity</span>
          <strong>{capability.maturity}</strong>
        </div>
        <div>
          <span>Confidence</span>
          <strong>{capability.confidence.toFixed(2)}</strong>
        </div>
      </div>
      <div className="signal-list" aria-label="Maturity evidence dimensions">
        {signalEntries.map(([name, present]) => (
          <span className={present ? 'signal signal--present' : 'signal'} key={name}>
            {present ? '✓' : '·'} {name}
          </span>
        ))}
      </div>
      <EvidenceGroup title="Code evidence" items={grouped.code} />
      <EvidenceGroup title="History evidence" items={grouped.history} />
      <EvidenceGroup title="Quality & documentation" items={grouped.quality} />
    </aside>
  )
}

function EvidenceGroup({ title, items }: { title: string; items: Evidence[] }) {
  return (
    <section className="evidence-group">
      <h3>
        {title} <span>{items.length}</span>
      </h3>
      {items.length ? (
        <ul>
          {items.slice(0, 16).map((item) => (
            <EvidenceRow evidence={item} key={item.id} />
          ))}
        </ul>
      ) : (
        <p className="empty-copy">No direct evidence in this dimension.</p>
      )}
    </section>
  )
}
