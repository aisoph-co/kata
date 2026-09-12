import { useAuth0 } from '@auth0/auth0-react'
import { ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * Screen 2 (W2)'s failure path B: this person resolved fine (Screen 1
 * passed) but has no `role` on record — a roster import (row 6/8) that ran
 * without one. No silent default, no "unknown" persona, nothing to confirm
 * — a fixed, explicit prompt, and the app never renders past this until a
 * roster re-import sets the role. Shaped like `SignInRefused`, but this is
 * a role gap, not an identity one.
 */
export function RoleRequired() {
  const { t } = useTranslation()
  const { logout } = useAuth0()

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm border-dashed" data-testid="role-required">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldAlert className="size-4 text-muted-foreground" />
            {t('roleConfirm.missingTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">{t('roleConfirm.missingBody')}</p>
          <Button
            variant="outline"
            data-testid="role-required-back"
            onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
          >
            {t('signIn.backToSignIn')}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
