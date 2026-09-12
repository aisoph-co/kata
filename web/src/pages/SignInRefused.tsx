import { useAuth0 } from '@auth0/auth0-react'
import { ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * Screen 1's fixed refusal screen — failure path A: the Auth0 profile's
 * email doesn't resolve to any roster person (`403 unknown_identity`), or
 * `email_verified` is false. No session is created and nothing here writes
 * to the identity table — resolution only ever reads the roster import.
 * Mirrors Hermes's unknown-identity refusal exactly, not a web-specific one.
 */
export function SignInRefused() {
  const { t } = useTranslation()
  const { logout } = useAuth0()

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm border-dashed" data-testid="sign-in-refused">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldAlert className="size-4 text-muted-foreground" />
            {t('signIn.refusedTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">{t('signIn.refusedBody')}</p>
          <Button
            variant="outline"
            data-testid="sign-in-refused-retry"
            onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
          >
            {t('signIn.backToSignIn')}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
