import { useId, useState, type FormEvent } from 'react'

interface AnalysisFormProps {
  onAnalyze: (url: string) => Promise<void>
  loading: boolean
  compact?: boolean
}

const githubPattern = /^https:\/\/github\.com\/[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_.-]*(?:\.git)?\/?$/

export function AnalysisForm({ onAnalyze, loading, compact = false }: AnalysisFormProps) {
  const inputId = useId()
  const [url, setUrl] = useState('')
  const [validation, setValidation] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = url.trim()
    if (!githubPattern.test(value)) {
      setValidation('Use a public URL in the form https://github.com/owner/repository')
      return
    }
    setValidation(null)
    await onAnalyze(value)
  }

  return (
    <form className={`analysis-form ${compact ? 'analysis-form--compact' : ''}`} onSubmit={submit}>
      <label className="sr-only" htmlFor={inputId}>
        Public GitHub repository URL
      </label>
      <div className="url-control">
        <span aria-hidden="true" className="url-control__mark">
          ⑂
        </span>
        <input
          id={inputId}
          type="url"
          value={url}
          disabled={loading}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://github.com/owner/repository"
          autoComplete="url"
          spellCheck={false}
          aria-describedby={validation ? `${inputId}-error` : undefined}
          aria-invalid={Boolean(validation)}
        />
      </div>
      <button className="button button--primary" disabled={loading} type="submit">
        {loading ? 'Reading evidence…' : 'Analyze repository'}
        {!loading && <span aria-hidden="true">↗</span>}
      </button>
      {validation && (
        <p className="form-error" id={`${inputId}-error`} role="alert">
          {validation}
        </p>
      )}
    </form>
  )
}
