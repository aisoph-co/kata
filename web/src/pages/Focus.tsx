import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { DataState } from '@/components/DataState'
import { PageScaffold } from '@/components/PageScaffold'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useApiQuery } from '@/hooks/useApiQuery'
import { useLangPath } from '@/hooks/useLangPath'
import { ApiError, apiFetch } from '@/lib/api-client'
import { addCreatedFocus, type FocusOut, removeCreatedFocus, useCreatedFocuses } from '@/lib/focus-store'
import { errorExplanation } from '@/lib/error-explanations'
import { formatDateTime } from '@/lib/format'
import { CONCEPTS, conceptTitle, personName } from '@/lib/ferry-scenario'
import { setPersonaId, usePersona } from '@/lib/persona-store'

interface TeamOverview {
  concepts: { concept_id: string }[]
  people: { person_id: string }[]
}

export function Focus() {
  const { t } = useTranslation()
  const persona = usePersona()
  const navigate = useNavigate()
  const langPath = useLangPath()
  const overview = useApiQuery<TeamOverview>('team-overview', '/team/overview')
  const created = useCreatedFocuses()

  const [scopeKind, setScopeKind] = useState('person')
  const [scopePersonId, setScopePersonId] = useState('')
  const [conceptId, setConceptId] = useState('')
  const [weight, setWeight] = useState('1.5')
  const [expiresAt, setExpiresAt] = useState('')

  const create = useMutation({
    mutationFn: () =>
      apiFetch<FocusOut>('/team/focus', {
        persona,
        method: 'POST',
        body: {
          scope_kind: scopeKind,
          scope_person_id: scopePersonId,
          concept_id: conceptId,
          weight: Number(weight),
          expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        },
      }),
    onSuccess: addCreatedFocus,
  })

  const remove = useMutation({
    mutationFn: (id: string) => apiFetch(`/team/focus/${id}`, { persona, method: 'DELETE' }),
    onSuccess: (_data, id) => removeCreatedFocus(id),
  })

  const people = overview.data?.people ?? []
  const canSubmit = scopePersonId !== '' && conceptId !== '' && Number(weight) > 0

  const createError = create.error
  const createCode = createError instanceof ApiError ? createError.code : undefined
  const createMessage = createError instanceof ApiError ? createError.message : String(createError ?? '')
  const createExplanation = errorExplanation(createCode)

  return (
    <PageScaffold title={t('focus.title')} description={t('focus.description')}>
      <div className="flex flex-col gap-6">
        <DataState query={overview} screen={t('focus.title')} isEmpty={() => false}>
          {() => (
            <Card>
              <CardContent className="grid gap-4 py-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label>{t('focus.scopeLabel')}</Label>
                  <Select value={scopeKind} onValueChange={setScopeKind}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="person">{t('focus.scopePerson')}</SelectItem>
                      <SelectItem value="subtree">{t('focus.scopeSubtree')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>{t('focus.personLabel')}</Label>
                  <Select value={scopePersonId} onValueChange={setScopePersonId}>
                    <SelectTrigger>
                      <SelectValue placeholder={t('focus.personPlaceholder')} />
                    </SelectTrigger>
                    <SelectContent>
                      {people.map((p) => (
                        <SelectItem key={p.person_id} value={p.person_id}>
                          {personName(p.person_id)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>{t('focus.conceptLabel')}</Label>
                  <Select value={conceptId} onValueChange={setConceptId}>
                    <SelectTrigger>
                      <SelectValue placeholder={t('focus.conceptPlaceholder')} />
                    </SelectTrigger>
                    <SelectContent>
                      {CONCEPTS.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>{t('focus.weightLabel')}</Label>
                  <Input type="number" min={0.1} step={0.1} value={weight} onChange={(e) => setWeight(e.target.value)} />
                </div>
                <div className="flex flex-col gap-1.5 sm:col-span-2">
                  <Label>{t('focus.expiresLabel')}</Label>
                  <Input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
                </div>
              </CardContent>
            </Card>
          )}
        </DataState>

        <div className="flex items-center gap-3">
          <Button disabled={!canSubmit || create.isPending} onClick={() => create.mutate()}>
            {t('focus.createButton')}
          </Button>
          {create.isError && (
            <span className="text-xs text-destructive">
              {createCode && <span className="mr-1 font-mono">{createCode}:</span>}
              {createMessage}
              {createExplanation && <span className="ml-1 text-destructive/70">· {createExplanation}</span>}
            </span>
          )}
        </div>

        <Card className={created.length === 0 ? 'border-dashed' : undefined}>
          <CardContent className="flex flex-col gap-3 py-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {created.length === 0 ? t('focus.noFocusesYet') : t('focus.createdThisSession')}
              </span>
              <Button
                variant="link"
                size="sm"
                onClick={() => {
                  setPersonaId('hugo')
                  navigate(langPath('/next-up'))
                }}
              >
                {t('focus.seeHugoQueue')}
              </Button>
            </div>
            {created.map((f) => (
              <div key={f.id} className="flex items-center justify-between rounded border p-2 text-sm">
                <div>
                  <p>
                    {t('focus.focusSummary', {
                      concept: conceptTitle(f.concept_id),
                      person: personName(f.scope_person_id),
                      kind: f.scope_kind,
                      weight: f.weight,
                    })}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t('focus.createdAt', { date: formatDateTime(f.created_at) })}
                    {f.expires_at && t('focus.expiresAt', { date: formatDateTime(f.expires_at) })}
                  </p>
                </div>
                <Button size="sm" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(f.id)}>
                  {t('focus.deleteButton')}
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </PageScaffold>
  )
}
