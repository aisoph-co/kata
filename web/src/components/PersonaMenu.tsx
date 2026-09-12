import { useAuth0 } from '@auth0/auth0-react'
import { AlertCircle, ChevronDown, Loader2, LogOut, WifiOff } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useResolvedIdentity } from '@/hooks/useResolvedIdentity'
import { ApiError } from '@/lib/api-client'
import { AUTH_ENABLED } from '@/lib/auth-config'
import { PERSONAS, type Persona } from '@/lib/personas'
import { getPersonaId, setPersonaId, usePersona } from '@/lib/persona-store'
import { cn } from '@/lib/utils'

function initials(name: string): string {
  return name.slice(0, 2).toUpperCase()
}

function PersonaAvatar({ persona, className }: { persona: Persona; className?: string }) {
  return (
    <Avatar className={cn('size-8', className)}>
      <AvatarFallback
        className="text-xs font-semibold text-white"
        style={{ backgroundColor: persona.avatarColor }}
      >
        {initials(persona.name)}
      </AvatarFallback>
    </Avatar>
  )
}

function PersonaMenuRow({ persona, isActive }: { persona: Persona; isActive: boolean }) {
  const { t } = useTranslation()
  return (
    <DropdownMenuItem
      data-testid={`persona-${persona.id}`}
      className={cn('gap-2.5 py-2', isActive && 'bg-secondary/60')}
      onSelect={() => setPersonaId(persona.id)}
    >
      <PersonaAvatar persona={persona} className="size-6" />
      <span className="flex flex-col leading-tight">
        <span className="text-sm">{persona.name}</span>
        {persona.role !== 'unknown' && (
          <span className="text-[11px] font-normal text-muted-foreground" data-testid="persona-role-channel">
            {t(`personaBar.role.${persona.role}`)} · {persona.channel}
          </span>
        )}
      </span>
    </DropdownMenuItem>
  )
}

/** Resolve status line under the current identity's name in the trigger —
 * a real POST /identities/resolve, not a client-side guess. */
function ResolveLine() {
  const { t } = useTranslation()
  const query = useResolvedIdentity()

  if (query.isLoading) {
    return (
      <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <Loader2 className="size-3 animate-spin" /> {t('personaBar.resolving')}
      </span>
    )
  }
  if (query.isError) {
    const error = query.error
    if (error instanceof ApiError && error.isUnreachable) {
      return (
        <span className="flex items-center gap-1 text-[11px] text-destructive">
          <WifiOff className="size-3" /> {t('personaBar.apiUnreachable')}
        </span>
      )
    }
    const code = error instanceof ApiError ? error.code : undefined
    return (
      <span className="flex items-center gap-1 text-[11px] text-destructive">
        <AlertCircle className="size-3" /> {code ?? t('apiStatus.fallbackCode')}
      </span>
    )
  }
  const person = query.data
  return (
    <span className="text-[11px] text-muted-foreground">
      {person?.display_name}
      {person?.is_operator && ` · ${t('personaBar.operatorSuffix')}`}
    </span>
  )
}

/** Top-right avatar menu — replaces the old chip bar. 5 primary personas
 * always listed, "More people" expands the secondary cast inline, Unknown
 * is always last and separated (it never resolves — 403 by design). */
export function PersonaMenu() {
  const { t } = useTranslation()
  const { logout } = useAuth0()
  const active = usePersona()
  const [open, setOpen] = useState(false)
  const [showMore, setShowMore] = useState(false)
  const primary = PERSONAS.filter((p) => !p.secondary && p.id !== 'unknown')
  const secondary = PERSONAS.filter((p) => p.secondary)
  const unknown = PERSONAS.find((p) => p.id === 'unknown')!
  const activeIsSecondary = secondary.some((p) => p.id === active.id)
  const activeId = active.id ?? getPersonaId()

  return (
    <DropdownMenu
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setShowMore(false)
      }}
    >
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          data-testid="persona-menu-trigger"
          className="flex items-center gap-2 rounded-full py-1 pr-1 pl-1.5 text-left transition-colors hover:bg-muted"
        >
          <PersonaAvatar persona={active} />
          <span className="hidden flex-col leading-tight sm:flex">
            <span className="text-sm font-medium">{active.name}</span>
            <ResolveLine />
          </span>
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="min-w-64">
        {primary.map((persona) => (
          <PersonaMenuRow key={persona.id} persona={persona} isActive={persona.id === activeId} />
        ))}
        {secondary.length > 0 && (
          <>
            <DropdownMenuItem
              data-testid="persona-more-toggle"
              className="justify-between text-muted-foreground"
              onSelect={(e) => {
                e.preventDefault()
                setShowMore((v) => !v)
              }}
            >
              {t('personaBar.morePeople')}
              <ChevronDown className={cn('size-3.5 transition-transform', (showMore || activeIsSecondary) && 'rotate-180')} />
            </DropdownMenuItem>
            {(showMore || activeIsSecondary) &&
              secondary.map((persona) => (
                <PersonaMenuRow key={persona.id} persona={persona} isActive={persona.id === activeId} />
              ))}
          </>
        )}
        <DropdownMenuSeparator />
        <PersonaMenuRow persona={unknown} isActive={unknown.id === activeId} />
        {AUTH_ENABLED && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              data-testid="sign-out"
              className="gap-2.5 text-muted-foreground"
              onSelect={() => logout({ logoutParams: { returnTo: window.location.origin } })}
            >
              <LogOut className="size-4" />
              {t('personaBar.signOut')}
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
