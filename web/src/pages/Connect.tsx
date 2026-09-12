import { CheckCircle2, Loader2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PlatformIcon } from '@/components/connect/PlatformIcon'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { type Platform, PLATFORMS, setConnected, useConnectState } from '@/lib/connect-store'

const STEP_KEYS = ['connect.stepAuth', 'connect.stepChannels', 'connect.stepMembers', 'connect.stepThreads'] as const
const STEP_DURATION_MS = 750

type DialogStage = 'authorize' | 'progress' | 'done'

function ConnectDialog({ platform, onClose }: { platform: Platform; onClose: () => void }) {
  const { t } = useTranslation()
  const [stage, setStage] = useState<DialogStage>('authorize')
  const [step, setStep] = useState(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (stage !== 'progress') return
    if (step >= STEP_KEYS.length) {
      setConnected(platform.id, true)
      setStage('done')
      return
    }
    timerRef.current = setTimeout(() => setStep((s) => s + 1), STEP_DURATION_MS)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [stage, step, platform.id])

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid="connect-dialog">
        {stage === 'authorize' && (
          <>
            <div className="-mx-6 -mt-6 flex items-center gap-3 rounded-t-xl px-6 py-5" style={{ backgroundColor: platform.color }}>
              <PlatformIcon platform={platform} size={32} />
              <span className="font-heading text-base font-semibold text-white">{platform.name}</span>
            </div>
            <DialogHeader className="pt-4">
              <DialogTitle>{t('connect.dialogTitle')}</DialogTitle>
              <DialogDescription>{t('connect.dialogBody', { platform: platform.name })}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={onClose} data-testid="connect-dialog-cancel">
                {t('connect.dialogCancel')}
              </Button>
              <Button
                onClick={() => setStage('progress')}
                data-testid="connect-dialog-allow"
                style={{ backgroundColor: platform.color }}
              >
                {t('connect.dialogAllow')}
              </Button>
            </DialogFooter>
          </>
        )}

        {stage === 'progress' && (
          <div className="flex flex-col gap-4 py-2" data-testid="connect-dialog-progress">
            <DialogHeader>
              <DialogTitle>{t('connect.progressTitle', { platform: platform.name })}</DialogTitle>
            </DialogHeader>
            <Progress value={(Math.min(step, STEP_KEYS.length) / STEP_KEYS.length) * 100} />
            <ul className="flex flex-col gap-2 text-sm">
              {STEP_KEYS.map((key, i) => (
                <li key={key} className="flex items-center gap-2">
                  {i < step ? (
                    <CheckCircle2 className="size-4 text-kata-good" />
                  ) : i === step ? (
                    <Loader2 className="size-4 animate-spin text-primary" />
                  ) : (
                    <span className="size-4 rounded-full border" />
                  )}
                  <span className={i > step ? 'text-muted-foreground' : ''}>{t(key)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {stage === 'done' && (
          <div className="flex flex-col items-center gap-3 py-4 text-center" data-testid="connect-dialog-done">
            <CheckCircle2 className="size-10 text-kata-good" />
            <p className="font-heading text-base font-semibold">{t('connect.connectedTitle', { platform: platform.name })}</p>
            <Button onClick={onClose}>{t('connect.done')}</Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function statLabel(t: (k: string) => string, key: 'channels' | 'membersMapped' | 'threads', platform: Platform) {
  if (key === 'channels' && platform.statLabelOverride?.channels) return platform.statLabelOverride.channels
  if (key === 'threads' && platform.statLabelOverride?.threads) return platform.statLabelOverride.threads
  return t(`connect.stat.${key}`)
}

function PlatformTile({ platform }: { platform: Platform }) {
  const { t } = useTranslation()
  const connected = useConnectState()
  const [dialogOpen, setDialogOpen] = useState(false)
  const isOn = !!connected[platform.id]

  return (
    <Card data-testid={`platform-tile-${platform.id}`} className={isOn ? 'border-primary/40' : undefined}>
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <PlatformIcon platform={platform} />
          <span className="font-medium">{platform.name}</span>
          {isOn && (
            <span className="ml-auto rounded-full bg-kata-good-2 px-2 py-0.5 text-[11px] font-medium text-kata-good" data-testid="connected-badge">
              {t('connect.connectedBadge')}
            </span>
          )}
        </div>

        {isOn ? (
          <>
            <div className="grid grid-cols-3 gap-2 text-center text-xs" data-testid="connected-stats">
              <div>
                <p className="font-heading text-base font-semibold">{platform.stats.channels}</p>
                <p className="text-muted-foreground">{statLabel(t, 'channels', platform)}</p>
              </div>
              <div>
                <p className="font-heading text-base font-semibold">{platform.stats.membersMapped}</p>
                <p className="text-muted-foreground">{t('connect.stat.membersMapped')}</p>
              </div>
              <div>
                <p className="font-heading text-base font-semibold">{platform.stats.threads}</p>
                <p className="text-muted-foreground">{statLabel(t, 'threads', platform)}</p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              data-testid={`disconnect-${platform.id}`}
              onClick={() => setConnected(platform.id, false)}
            >
              {t('connect.disconnectButton')}
            </Button>
          </>
        ) : (
          <Button size="sm" data-testid={`connect-${platform.id}`} onClick={() => setDialogOpen(true)}>
            {t('connect.connectButton')}
          </Button>
        )}
      </CardContent>
      {dialogOpen && <ConnectDialog platform={platform} onClose={() => setDialogOpen(false)} />}
    </Card>
  )
}

export function Connect() {
  const { t } = useTranslation()

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">{t('connect.title')}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('connect.description')}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLATFORMS.map((platform) => (
          <PlatformTile key={platform.id} platform={platform} />
        ))}
      </div>
    </div>
  )
}
