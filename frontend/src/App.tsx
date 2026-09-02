import { useEffect, useState } from 'react'
import { analyzeRepository } from './api'
import { AnalysisForm } from './components/AnalysisForm'
import { AnalysisSummary } from './components/AnalysisSummary'
import { CategoryOverview } from './components/CategoryOverview'
import { ConstellationView } from './components/ConstellationView'
import { EvidencePanel } from './components/EvidencePanel'
import { GraphView } from './components/GraphView'
import { RepositoryHeader } from './components/RepositoryHeader'
import { ReverseRoadmap } from './components/ReverseRoadmap'
import { WorkspaceNavigation } from './components/WorkspaceNavigation'
import type { AnalysisResult, Capability, GraphProjection } from './types'

export type View = 'constellation' | 'roadmap' | 'code' | 'workflows' | 'data'

const phases = [
  'Cloning within the safety boundary',
  'Reading source structure',
  'Tracing relationships and entry points',
  'Reconstructing capability history',
]

function App() {
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [phase, setPhase] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<View>('constellation')
  const [selected, setSelected] = useState<Capability | null>(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<Capability['category'] | 'ALL'>('ALL')

  useEffect(() => {
    if (!loading) return
    const timer = window.setInterval(
      () => setPhase((current) => Math.min(current + 1, phases.length - 1)),
      2300,
    )
    return () => window.clearInterval(timer)
  }, [loading])

  async function analyze(url: string) {
    setLoading(true)
    setPhase(0)
    setError(null)
    setSelected(null)
    try {
      const analysis = await analyzeRepository(url)
      setResult(analysis)
      setView('constellation')
      setQuery('')
      setCategory('ALL')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'RoadTrace could not analyze this repository.')
    } finally {
      setLoading(false)
    }
  }

  if (!result) {
    return (
      <div className="app-shell app-shell--landing">
        <TopBar />
        <main className="landing">
          <div className="landing__grid" aria-hidden="true" />
          <section className="hero">
            <p className="eyebrow">Software archaeology, made legible</p>
            <h1>
              From code history
              <br />
              to <em>living roadmap.</em>
            </h1>
            <p className="hero__copy">
              Paste a public GitHub repository. RoadTrace reads the source, traces its evolution,
              and shows what was actually built—with the evidence attached.
            </p>
            <AnalysisForm loading={loading} onAnalyze={analyze} />
            {error && (
              <div className="error-banner" role="alert">
                <span>!</span>
                <p>{error}</p>
              </div>
            )}
            {loading && <AnalysisProgress phase={phase} />}
            {!loading && (
              <div className="trust-line">
                <span>Read-only analysis</span>
                <span>Public repositories only</span>
                <span>No code execution</span>
              </div>
            )}
          </section>
          <aside className="hero-aside" aria-label="RoadTrace analysis model">
            <div className="layer-card layer-card--observed">
              <span>01 / OBSERVED</span>
              <strong>Source · structure · history</strong>
            </div>
            <div className="layer-connector" />
            <div className="layer-card layer-card--inferred">
              <span>02 / INFERRED</span>
              <strong>Capabilities · maturity · evolution</strong>
            </div>
            <div className="layer-connector" />
            <div className="layer-card layer-card--visible">
              <span>03 / VISIBLE</span>
              <strong>Roadmap · graph · evidence</strong>
            </div>
          </aside>
        </main>
        <footer className="landing-footer">
          <span>Evidence before inference.</span>
          <span>RoadTrace V0.1</span>
        </footer>
      </div>
    )
  }

  const activeGraph: GraphProjection | null =
    view === 'code'
        ? result.code_graph
        : view === 'workflows'
          ? result.workflow_graph
          : view === 'data'
            ? result.data_graph
            : null

  return (
    <div className="app-shell app-shell--analysis">
      <TopBar onReset={() => setResult(null)} />
      <main className="analysis-main">
        <RepositoryHeader repository={result.repository} />
        <AnalysisSummary result={result} />
        {result.warnings.length > 0 && (
          <details className="warning-banner">
            <summary>{result.warnings.length} bounded-analysis notice{result.warnings.length > 1 ? 's' : ''}</summary>
            <ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </details>
        )}
        <WorkspaceNavigation
          categories={result.categories}
          category={category}
          onCategoryChange={setCategory}
          onQueryChange={setQuery}
          onViewChange={(nextView) => {
            setView(nextView)
            setQuery('')
            if (!['constellation', 'roadmap'].includes(nextView)) setCategory('ALL')
          }}
          query={query}
          view={view}
        />
        <div className="view-content">
          {view === 'constellation' ? (
            <>
              <CategoryOverview
                activeCategory={category}
                capabilities={result.capabilities}
                categories={result.categories}
                onCategoryChange={setCategory}
                onSelect={setSelected}
                query={query}
              />
              <ConstellationView
                activeCategory={category}
                capabilities={result.capabilities}
                graph={result.capability_graph}
                onCategoryChange={setCategory}
                onSelectCapability={setSelected}
                query={query}
                repositoryName={result.repository.name}
              />
            </>
          ) : view === 'roadmap' ? (
            <ReverseRoadmap
              category={category}
              query={query}
              result={result}
              onSelectCapability={setSelected}
            />
          ) : (
            activeGraph && (
              <GraphView
                key={view}
                graph={activeGraph}
                capabilities={result.capabilities}
                onSelectCapability={setSelected}
                query={query}
              />
            )
          )}
        </div>
      </main>
      {selected && <button aria-label="Close evidence panel" className="panel-scrim" onClick={() => setSelected(null)} type="button" />}
      <EvidencePanel capability={selected} result={result} onClose={() => setSelected(null)} />
    </div>
  )
}

function TopBar({ onReset }: { onReset?: () => void }) {
  return (
    <header className="topbar">
      <button className="wordmark" onClick={onReset} type="button" disabled={!onReset}>
        <span className="wordmark__symbol">R<span>T</span></span>
        <span>ROADTRACE</span>
      </button>
      <p>From code history to living roadmap.</p>
      {onReset && (
        <button className="button button--quiet" onClick={onReset} type="button">
          Analyze another <span aria-hidden="true">＋</span>
        </button>
      )}
    </header>
  )
}

function AnalysisProgress({ phase }: { phase: number }) {
  return (
    <div aria-live="polite" className="analysis-progress">
      <div className="spinner" aria-hidden="true" />
      <div>
        <strong>{phases[phase]}</strong>
        <p>RoadTrace never runs repository code.</p>
      </div>
      <span>{String(phase + 1).padStart(2, '0')} / 04</span>
    </div>
  )
}

export default App
