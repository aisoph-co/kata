import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { type BackstageCall, clearBackstage, useBackstageCalls } from '@/lib/backstage-store'
import { ANSWER_KEY_FIELDS } from '@/lib/format'
import { cn } from '@/lib/utils'

function statusVariant(status: number): 'default' | 'destructive' | 'secondary' {
  if (status === 0) return 'destructive'
  if (status >= 500) return 'destructive'
  if (status >= 400) return 'secondary'
  return 'default'
}

// The service strips answer-key fields from item payloads before a learner
// ever sees them (agency-v1 engine/models.py ANSWER_KEY_FIELDS) — this
// checks the actual response for their absence rather than asserting it.
function strippedFieldsNote(call: BackstageCall, t: (key: string, opts?: Record<string, unknown>) => string): string | null {
  if (!(call.path.startsWith('/me/next') && call.method === 'GET')) return null
  const items = (call.response as { items?: { payload?: Record<string, unknown> }[] } | null)?.items
  if (!items?.length) return null
  const present = ANSWER_KEY_FIELDS.filter((field) => items.some((item) => field in (item.payload ?? {})))
  const missing = ANSWER_KEY_FIELDS.filter((f) => !present.includes(f))
  return t('backstage.strippedNote', { fields: missing.join(', ') })
}

export function BackstageDrawer({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation()
  const calls = useBackstageCalls()

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-lg">
        <SheetHeader className="flex-row items-center justify-between gap-2 space-y-0">
          <div>
            <SheetTitle>{t('backstage.title')}</SheetTitle>
            <SheetDescription>{t('backstage.description', { count: calls.length })}</SheetDescription>
          </div>
          <Button size="sm" variant="ghost" onClick={clearBackstage} disabled={calls.length === 0}>
            {t('backstage.clear')}
          </Button>
        </SheetHeader>
        <div className="flex flex-col gap-2 overflow-y-auto px-4 pb-6">
          {calls.length === 0 && <p className="text-sm text-muted-foreground">{t('backstage.noCalls')}</p>}
          {calls.map((call) => {
            const note = strippedFieldsNote(call, t)
            return (
              <details key={call.id} className="group rounded-lg border">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm">
                  <Badge variant={call.local ? 'outline' : statusVariant(call.status)} className="font-mono">
                    {call.local ? 'LOCAL' : call.status || 'ERR'}
                  </Badge>
                  <span className="font-mono text-xs text-muted-foreground">{call.method}</span>
                  <span className="flex-1 truncate font-mono text-xs">{call.path}</span>
                  {!call.local && <span className="text-xs text-muted-foreground">{Math.round(call.durationMs)}ms</span>}
                </summary>
                <div className={cn('space-y-3 border-t px-3 py-3 text-xs')}>
                  <div>
                    <p className="mb-1 font-medium text-muted-foreground">{t('backstage.requestHeaders')}</p>
                    <pre className="overflow-x-auto rounded bg-muted p-2 font-mono">
                      {JSON.stringify(call.headers, null, 2)}
                    </pre>
                  </div>
                  {call.body != null && (
                    <div>
                      <p className="mb-1 font-medium text-muted-foreground">{t('backstage.requestBody')}</p>
                      <pre className="overflow-x-auto rounded bg-muted p-2 font-mono">
                        {JSON.stringify(call.body, null, 2)}
                      </pre>
                    </div>
                  )}
                  <div>
                    <p className="mb-1 font-medium text-muted-foreground">{t('backstage.response')}</p>
                    <pre className="overflow-x-auto rounded bg-muted p-2 font-mono">
                      {JSON.stringify(call.response, null, 2)}
                    </pre>
                    {note && <p className="mt-1 text-[11px] italic text-muted-foreground">{note}</p>}
                  </div>
                </div>
              </details>
            )
          })}
        </div>
      </SheetContent>
    </Sheet>
  )
}
