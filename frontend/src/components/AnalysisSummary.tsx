import type { AnalysisResult } from '../types'

export function AnalysisSummary({ result }: { result: AnalysisResult }) {
  const linkedEvidence = new Set(result.capabilities.flatMap((item) => item.evidence_ids)).size
  const qualityBacked = result.capabilities.filter(
    (item) => item.maturity_signals.tests || item.maturity_signals.validation,
  ).length
  const historyLabel = result.commits.length ? result.commits.length.toLocaleString() : '—'

  return (
    <dl className="analysis-summary" aria-label="Repository analysis summary">
      <Metric label="Capabilities found" value={result.capabilities.length.toLocaleString()} />
      <Metric label="Quality-backed capabilities" value={qualityBacked.toLocaleString()} />
      <Metric label="Linked evidence items" value={linkedEvidence.toLocaleString()} />
      <Metric label="Commits observed" value={historyLabel} />
      <Metric label="Files analyzed" value={result.repository.files_analyzed.toLocaleString()} />
    </dl>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}
