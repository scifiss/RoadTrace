import type { AnalysisResult } from './types'

const API_ROOT = import.meta.env.VITE_API_URL?.replace(/\/$/, '') ?? ''
const API_UNAVAILABLE =
  'RoadTrace API is unavailable. Start the backend in a second terminal or run ./scripts/dev.sh from the project root.'

export async function analyzeRepository(repositoryUrl: string): Promise<AnalysisResult> {
  let response: Response
  try {
    response = await fetch(`${API_ROOT}/api/analyses`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repository_url: repositoryUrl }),
    })
  } catch {
    throw new Error(API_UNAVAILABLE)
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    if (payload?.detail) throw new Error(payload.detail)
    if (response.status >= 500) {
      throw new Error(`${API_UNAVAILABLE} The proxy returned HTTP ${response.status}.`)
    }
    throw new Error(`RoadTrace could not analyze this repository (HTTP ${response.status}).`)
  }
  return response.json() as Promise<AnalysisResult>
}
