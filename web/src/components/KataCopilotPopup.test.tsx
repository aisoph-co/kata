import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCopilotAuthHeaders } from '@/hooks/useCopilotAuthHeaders'
import type { WebSession } from '@/lib/session-store'
import { useWebSession } from '@/lib/session-store'

vi.mock('@/lib/session-store', () => ({ useWebSession: vi.fn() }))
vi.mock('@/hooks/useCopilotAuthHeaders', () => ({ useCopilotAuthHeaders: vi.fn() }))
vi.mock('@copilotkit/react-core', () => ({
  CopilotKit: ({ runtimeUrl, headers, children }: { runtimeUrl: string; headers: unknown; children: unknown }) => (
    <div data-testid="copilotkit" data-runtime-url={runtimeUrl} data-headers={JSON.stringify(headers)}>
      {children as never}
    </div>
  ),
}))
vi.mock('@copilotkit/react-ui', () => ({
  CopilotPopup: ({ labels }: { labels: { title: string } }) => <div data-testid="copilot-popup">{labels.title}</div>,
}))

import { KataCopilotPopup } from './KataCopilotPopup'

const mockUseWebSession = vi.mocked(useWebSession)
const mockUseAuthHeaders = vi.mocked(useCopilotAuthHeaders)

const SESSION: WebSession = {
  personId: 'p1',
  displayName: 'Hugo',
  email: 'hugo@ferry.example',
  isOperator: false,
  role: 'senior_swe',
  header: 'web:auth0|hugo',
}

const HAD_ORIGINAL_ENV = 'VITE_COPILOTKIT_RUNTIME_URL' in import.meta.env
const ORIGINAL_ENV = import.meta.env.VITE_COPILOTKIT_RUNTIME_URL

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  if (HAD_ORIGINAL_ENV) {
    import.meta.env.VITE_COPILOTKIT_RUNTIME_URL = ORIGINAL_ENV
  } else {
    delete import.meta.env.VITE_COPILOTKIT_RUNTIME_URL
  }
})

describe('KataCopilotPopup', () => {
  it('renders nothing with no signed-in session', () => {
    import.meta.env.VITE_COPILOTKIT_RUNTIME_URL = 'https://runtime.example/copilotkit'
    mockUseWebSession.mockReturnValue(null)
    mockUseAuthHeaders.mockReturnValue({})

    const { container } = render(<KataCopilotPopup />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when no runtime URL is reserved for this deployment', () => {
    delete import.meta.env.VITE_COPILOTKIT_RUNTIME_URL
    mockUseWebSession.mockReturnValue(SESSION)
    mockUseAuthHeaders.mockReturnValue({})

    const { container } = render(<KataCopilotPopup />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing while the auth header is still resolving (undefined)', () => {
    import.meta.env.VITE_COPILOTKIT_RUNTIME_URL = 'https://runtime.example/copilotkit'
    mockUseWebSession.mockReturnValue(SESSION)
    mockUseAuthHeaders.mockReturnValue(undefined)

    const { container } = render(<KataCopilotPopup />)
    expect(container).toBeEmptyDOMElement()
  })

  it('mounts the popup behind CopilotKit, pointed at the absolute runtime URL, once a session and headers are ready', () => {
    import.meta.env.VITE_COPILOTKIT_RUNTIME_URL = 'https://runtime.example/copilotkit'
    mockUseWebSession.mockReturnValue(SESSION)
    mockUseAuthHeaders.mockReturnValue({ Authorization: 'Bearer signed.jwt.token' })

    render(<KataCopilotPopup />)

    const provider = screen.getByTestId('copilotkit')
    expect(provider.dataset.runtimeUrl).toBe('https://runtime.example/copilotkit')
    expect(provider.dataset.headers).toBe(JSON.stringify({ Authorization: 'Bearer signed.jwt.token' }))
    expect(screen.getByTestId('copilot-popup')).toHaveTextContent('Kata')
  })
})
