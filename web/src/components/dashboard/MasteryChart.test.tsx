import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MASTERY_THRESHOLD, MasteryChart } from './MasteryChart'

describe('MasteryChart', () => {
  it('renders every locator test_dashboard.py asserts on, against the real seed fixture', () => {
    render(<MasteryChart />)

    const chart = screen.getByTestId('dashboard-mastery-chart')
    expect(chart).toHaveAttribute('data-concept', 'idempotency')
    expect(screen.getByTestId('mastery-threshold-line')).toHaveAttribute('data-value', String(MASTERY_THRESHOLD))
    expect(screen.getByTestId('bypass-event-annotation')).toBeInTheDocument()
    expect(screen.getByTestId('closing-question-recovery-annotation')).toBeInTheDocument()
    expect(screen.getByTestId('bypass-rate-series')).toBeInTheDocument()
  })

  it('renders exactly one bypass annotation and one recovery annotation — the one 1:15 beat, not every bypass in the window', () => {
    render(<MasteryChart />)
    expect(screen.getAllByTestId('bypass-event-annotation')).toHaveLength(1)
    expect(screen.getAllByTestId('closing-question-recovery-annotation')).toHaveLength(1)
  })
})
