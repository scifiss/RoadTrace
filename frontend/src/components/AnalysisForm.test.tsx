import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AnalysisForm } from './AnalysisForm'

describe('AnalysisForm', () => {
  it('rejects arbitrary URLs before analysis', async () => {
    const analyze = vi.fn(async () => undefined)
    render(<AnalysisForm loading={false} onAnalyze={analyze} />)
    fireEvent.change(screen.getByLabelText('Public GitHub repository URL'), {
      target: { value: 'https://example.com/owner/repo' },
    })
    fireEvent.click(screen.getByRole('button', { name: /analyze repository/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('public URL')
    expect(analyze).not.toHaveBeenCalled()
  })

  it('submits a canonical public GitHub URL', async () => {
    const analyze = vi.fn(async () => undefined)
    render(<AnalysisForm loading={false} onAnalyze={analyze} />)
    fireEvent.change(screen.getByLabelText('Public GitHub repository URL'), {
      target: { value: 'https://github.com/openai/openai-python' },
    })
    fireEvent.click(screen.getByRole('button', { name: /analyze repository/i }))
    expect(analyze).toHaveBeenCalledWith('https://github.com/openai/openai-python')
  })
})
