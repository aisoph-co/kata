import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/auth-config', () => ({ AUTH_ENABLED: false }))

import { SessionGate } from './SessionGate'

// No Auth0 tenant is configured in this workspace yet — the gate must be a
// pure passthrough, not just "renders quickly."
describe('SessionGate (AUTH_ENABLED = false)', () => {
  it('renders children directly with no sign-in gate at all', () => {
    render(
      <SessionGate>
        <div data-testid="app-child">app</div>
      </SessionGate>,
    )

    expect(screen.getByTestId('app-child')).toBeInTheDocument()
    expect(screen.queryByTestId('sign-in-button')).not.toBeInTheDocument()
  })
})
