import { afterEach, describe, expect, it, vi } from 'vitest'
import { analyzeRepository } from './api'

describe('analysis API errors', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('explains how to start the backend when fetch cannot connect', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(analyzeRepository('https://github.com/octocat/Hello-World')).rejects.toThrow(
      'Start the backend',
    )
  })

  it('explains a non-JSON development proxy failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('proxy failure', { status: 500 })))

    await expect(analyzeRepository('https://github.com/octocat/Hello-World')).rejects.toThrow(
      'proxy returned HTTP 500',
    )
  })

  it('preserves a structured error returned by the API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Repository must be public.' }), {
          headers: { 'Content-Type': 'application/json' },
          status: 422,
        }),
      ),
    )

    await expect(analyzeRepository('https://github.com/octocat/private')).rejects.toThrow(
      'Repository must be public.',
    )
  })
})
