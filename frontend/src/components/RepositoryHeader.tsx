import type { RepositorySummary } from '../types'

function formatDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat('en', { month: 'short', year: 'numeric' }).format(new Date(value))
    : 'Not available'
}

export function RepositoryHeader({ repository }: { repository: RepositorySummary }) {
  const languages = Object.keys(repository.languages)
  return (
    <header className="repository-header">
      <div>
        <p className="eyebrow">
          {repository.owner} / <span>{repository.default_branch ?? 'default'}</span>
        </p>
        <h1>{repository.name}</h1>
        <a href={repository.url} rel="noreferrer" target="_blank">
          View public repository <span aria-hidden="true">↗</span>
        </a>
      </div>
      <dl className="repository-stats">
        <div>
          <dt>Languages</dt>
          <dd>{languages.join(' · ') || 'No supported source'}</dd>
        </div>
        <div>
          <dt>History observed</dt>
          <dd>
            {formatDate(repository.history_start)} — {formatDate(repository.history_end)}
          </dd>
        </div>
        <div>
          <dt>Files analyzed</dt>
          <dd>{repository.files_analyzed.toLocaleString()}</dd>
        </div>
      </dl>
    </header>
  )
}
