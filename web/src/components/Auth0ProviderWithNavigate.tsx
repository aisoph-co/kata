import { Auth0Provider, type AppState } from '@auth0/auth0-react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { AUTH0_CLIENT_ID, AUTH0_DOMAIN, AUTH_ENABLED } from '@/lib/auth-config'

/**
 * Wraps the app in `Auth0Provider` only once a tenant is configured
 * (`AUTH_ENABLED`) — a no-op passthrough otherwise, which is every
 * deployment of this workspace today. Sits inside `<BrowserRouter>` on
 * purpose: the post-redirect callback needs `useNavigate` to land back on
 * the route the visitor started from, not a full page reload.
 */
export function Auth0ProviderWithNavigate({ children }: { children: ReactNode }) {
  const navigate = useNavigate()

  if (!AUTH_ENABLED) return <>{children}</>

  function onRedirectCallback(appState?: AppState) {
    navigate(appState?.returnTo ?? window.location.pathname)
  }

  return (
    <Auth0Provider
      domain={AUTH0_DOMAIN!}
      clientId={AUTH0_CLIENT_ID!}
      authorizationParams={{
        redirect_uri: window.location.origin,
      }}
      // SDK default (`cacheLocation: 'memory'`) loses the session on every
      // reload, forcing a silent-auth check in a hidden iframe against
      // `*.auth0.com` — a cross-site cookie that Safari, Firefox, and any
      // Chrome with 3P cookies blocked will never send, so refresh dumps a
      // signed-in visitor back on the sign-in card. `localstorage`
      // persists the still-valid token across reloads without one, and
      // needs no Auth0 dashboard change (unlike `useRefreshTokens`, which
      // requires an admin to enable rotation on the tenant).
      cacheLocation="localstorage"
      onRedirectCallback={onRedirectCallback}
    >
      {children}
    </Auth0Provider>
  )
}
