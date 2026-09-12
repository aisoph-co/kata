import { Auth0Provider, type AppState } from '@auth0/auth0-react'
import type { ReactNode } from 'react'
import { AUTH0_AUDIENCE, AUTH0_CLIENT_ID, AUTH0_DOMAIN, AUTH_ENABLED } from '@/lib/auth-config'

/**
 * Wraps the app in `Auth0Provider` only once a tenant is configured
 * (`AUTH_ENABLED`) — a no-op passthrough otherwise, which is every
 * deployment of this workspace today (`BRIEF.md`: "empty at 11:30").
 */
export function Auth0ProviderWithNavigate({ children }: { children: ReactNode }) {
  if (!AUTH_ENABLED) return <>{children}</>

  function onRedirectCallback(appState?: AppState) {
    // No router yet (W1 is the gate only) — just drop Auth0's query params
    // from the URL bar without a full reload.
    window.history.replaceState({}, document.title, appState?.returnTo ?? window.location.pathname)
  }

  return (
    <Auth0Provider
      domain={AUTH0_DOMAIN!}
      clientId={AUTH0_CLIENT_ID!}
      authorizationParams={{
        redirect_uri: window.location.origin,
        ...(AUTH0_AUDIENCE ? { audience: AUTH0_AUDIENCE } : {}),
      }}
      onRedirectCallback={onRedirectCallback}
    >
      {children}
    </Auth0Provider>
  )
}
