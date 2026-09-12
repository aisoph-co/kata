import { useAuth0 } from '@auth0/auth0-react'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

type Status = 'loading' | 'signed-out' | 'error' | 'unverified'

/**
 * Screen 1's landing page for a signed-out visitor — offers Auth0 login
 * (Slack connection if configured for the tenant, Google always available;
 * both are Auth0 Universal Login's choice, not this component's) and never
 * guesses or pre-fills an identity.
 *
 * Also covers Auth0's own loading state, its failure path (error or the
 * visitor cancels — back here with a retry action, no partial session, no
 * stack trace), and `unverified`: Auth0 already has a session for this
 * account, so offering "Sign in" again would just bounce straight back
 * here — sign out instead, so the visitor can try a different account.
 */
export function SignIn({ status, message }: { status: Status; message?: string }) {
  const { t } = useTranslation()
  const { loginWithRedirect, logout } = useAuth0()

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-center font-heading text-lg tracking-[0.14em] text-primary">
            {t('common.wordmark')}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4 text-center">
          {status === 'loading' && (
            <span className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="sign-in-loading">
              <Loader2 className="size-4 animate-spin" /> {t('signIn.loading')}
            </span>
          )}
          {status === 'error' && (
            <span className="flex items-center gap-2 text-sm text-destructive" data-testid="sign-in-error">
              <AlertCircle className="size-4" /> {message ?? t('signIn.genericError')}
            </span>
          )}
          {status === 'unverified' && (
            <>
              <span className="flex items-center gap-2 text-sm text-destructive" data-testid="sign-in-unverified">
                <AlertCircle className="size-4" /> {t('signIn.unverifiedBody')}
              </span>
              <Button
                variant="outline"
                data-testid="sign-in-unverified-signout"
                onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
              >
                {t('signIn.signOut')}
              </Button>
            </>
          )}
          {(status === 'signed-out' || status === 'error') && (
            <>
              <p className="text-sm text-muted-foreground">{t('signIn.blurb')}</p>
              <Button data-testid="sign-in-button" onClick={() => loginWithRedirect()}>
                {status === 'error' ? t('signIn.retry') : t('signIn.cta')}
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
