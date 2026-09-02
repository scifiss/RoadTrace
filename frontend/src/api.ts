import type { AnalysisResult } from './types'

const API_ROOT = import.meta.env.VITE_API_URL?.replace(/\/$/, '') ?? ''

export async function analyzeRepository(repositoryUrl: string): Promise<AnalysisResult> {
  const response = await fetch(`${API_ROOT}/api/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repository_url: repositoryUrl }),
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail ?? 'RoadTrace could not analyze this repository.')
  }
  return response.json() as Promise<AnalysisResult>
}
