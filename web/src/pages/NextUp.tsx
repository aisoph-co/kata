import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiStatusBanner } from '@/components/ApiStatusBanner'
import { DataState } from '@/components/DataState'
import { MasteryBar } from '@/components/MasteryBar'
import { PageScaffold } from '@/components/PageScaffold'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ApiError, apiFetch } from '@/lib/api-client'
import { recordLocalEvent } from '@/lib/backstage-store'
import { RATING_LABEL, formatDateTime } from '@/lib/format'
import { conceptTitle } from '@/lib/ferry-scenario'
import type { Persona } from '@/lib/personas'
import { usePersona } from '@/lib/persona-store'

// Maps 1:1 to GET /me/next's `limit` query param (API max is 20) — visible
// in Backstage on the request itself, nothing hidden about what was asked for.
const BATCH_SIZES = [5, 10, 20] as const
const DEFAULT_BATCH_SIZE = 5

interface NextItem {
  id: string
  concept_id: string
  kind: 'mcq' | 'msq' | 'self_rated' | 'short_answer' | 'teach_back'
  prompt: string
  payload: { options?: string[] }
}

interface NextResponse {
  items: NextItem[]
  reason: string | null
}

interface ReviewResult {
  grade: number
  rating: number
  correct: boolean
  explanation: string | null
  confidence: number | null
  bypassed: boolean
  next_due_at: string
  concept: { p_known: number; mastered: boolean }
}

function newIdempotencyKey(): string {
  return crypto.randomUUID()
}

/** teach_back can never be submitted (422 no_grader), so it's pushed to the
 * end of the on-screen order — the API's own order is untouched (still what
 * Backstage shows) and reachable via the Skip button either way. */
function reorderBatch(items: NextItem[]): { item: NextItem; moved: boolean }[] {
  const gradeable = items.filter((i) => i.kind !== 'teach_back')
  const teachBack = items.filter((i) => i.kind === 'teach_back')
  return [...gradeable, ...teachBack].map((item, newIndex) => ({
    item,
    moved: items.indexOf(item) !== newIndex,
  }))
}

function ResultPanel({ result, replay }: { result: ReviewResult; replay?: boolean }) {
  const { t } = useTranslation()
  return (
    <Card className={replay ? 'border-secondary' : 'border-mastery-high/40'}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {result.correct ? (
            <CheckCircle2 className="size-4 text-mastery-high" />
          ) : (
            <XCircle className="size-4 text-mastery-low" />
          )}
          {replay ? t('nextUp.replayBanner') : t('nextUp.graded')}
          <Badge variant="secondary">{RATING_LABEL[result.rating] ?? result.rating}</Badge>
          {result.bypassed && <Badge variant="outline">{t('nextUp.bypassedBadge')}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-muted-foreground">
          <span>{t('nextUp.resultGradeLabel')}</span>
          <span className="text-foreground">{result.grade}</span>
          <span>{t('nextUp.resultCorrectLabel')}</span>
          <span className="text-foreground">{result.correct ? t('nextUp.yes') : t('nextUp.no')}</span>
          <span>{t('nextUp.resultNextDueLabel')}</span>
          <span className="text-foreground">{formatDateTime(result.next_due_at)}</span>
          {result.confidence !== null && (
            <>
              <span>{t('nextUp.confidenceLabel')}</span>
              <span className="text-foreground">{result.confidence}</span>
            </>
          )}
        </div>
        {result.explanation && <p className="rounded bg-muted p-2 text-xs">{result.explanation}</p>}
        <div>
          <p className="mb-1 text-xs text-muted-foreground">{t('nextUp.resultPKnownLabel')}</p>
          <MasteryBar p={result.concept.p_known} />
        </div>
      </CardContent>
    </Card>
  )
}

/** Owns per-item answer/result state; keyed by item.id at the call site so a
 * fresh item remounts (and resets state) instead of needing an effect. */
function NextItemCard({
  item,
  persona,
  onSkip,
  onNext,
}: {
  item: NextItem
  persona: Persona
  onSkip: () => void
  onNext: () => void
}) {
  const { t } = useTranslation()
  const [idempotencyKey] = useState(newIdempotencyKey)
  const [choice, setChoice] = useState('')
  const [choices, setChoices] = useState<number[]>([])
  const [rating, setRating] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [result, setResult] = useState<ReviewResult | null>(null)
  const [replayResult, setReplayResult] = useState<ReviewResult | null>(null)
  const [confidence, setConfidence] = useState<number | null>(null)

  const submit = useMutation({
    mutationFn: ({ key, bypass }: { key: string; bypass: boolean }) => {
      // "Just tell me" sends no synthesised answer — `response: {}` is a
      // real, valid body for a bypass (the service still requires the
      // field, but ignores its content and caps the grade regardless).
      const response = bypass
        ? {}
        : item.kind === 'mcq'
          ? { choice: Number(choice) }
          : item.kind === 'msq'
            ? { choices }
            : item.kind === 'self_rated'
              ? { rating }
              : { text }
      const body: Record<string, unknown> = { item_id: item.id, idempotency_key: key, response }
      // confidence and bypassed are independent fields on one review (Contract
      // change #1) — bypassing must not silently drop calibration data.
      if (bypass) body.bypassed = true
      if (confidence !== null) body.confidence = confidence
      return apiFetch<ReviewResult>('/me/reviews', { persona, method: 'POST', body })
    },
    onSuccess: (data, { key }) => {
      if (key === idempotencyKey) {
        setResult(data)
        setReplayResult(null)
      }
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409 && error.code === 'idempotency_replay') {
        const body = error.body as { detail?: { result?: ReviewResult } } | undefined
        if (body?.detail?.result) setReplayResult(body.detail.result)
      }
    },
  })

  const canSubmit =
    (item.kind === 'mcq' && choice !== '') ||
    (item.kind === 'msq' && choices.length > 0) ||
    (item.kind === 'self_rated' && rating !== null) ||
    (item.kind === 'short_answer' && text.trim().length > 0)

  const graded = result !== null

  function handleSkip() {
    recordLocalEvent({
      label: `skip ${item.kind} ${item.id}`,
      note: t('backstage.skipEventNote'),
      detail: { item_id: item.id, kind: item.kind },
    })
    onSkip()
  }

  return (
    <div className="flex flex-col gap-4" data-testid="next-item-card" data-item-id={item.id} data-graded={graded}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span>{item.prompt}</span>
            <Badge variant="outline">{conceptTitle(item.concept_id)}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {item.kind === 'mcq' && (
            <RadioGroup value={choice} onValueChange={setChoice} data-testid="mcq-options">
              {item.payload.options?.map((opt, i) => (
                <div key={i} className="flex items-center gap-2">
                  <RadioGroupItem value={String(i)} id={`opt-${i}`} />
                  <Label htmlFor={`opt-${i}`} className="font-normal">
                    {opt}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          )}
          {item.kind === 'msq' && (
            <div className="flex flex-col gap-2" data-testid="msq-options">
              {item.payload.options?.map((opt, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Checkbox
                    id={`chk-${i}`}
                    checked={choices.includes(i)}
                    onCheckedChange={(checked) =>
                      setChoices((prev) => (checked ? [...prev, i] : prev.filter((x) => x !== i)))
                    }
                  />
                  <Label htmlFor={`chk-${i}`} className="font-normal">
                    {opt}
                  </Label>
                </div>
              ))}
            </div>
          )}
          {item.kind === 'self_rated' && (
            <div className="flex gap-2" data-testid="self-rated-options">
              {[1, 2, 3, 4].map((r) => (
                <Button
                  key={r}
                  type="button"
                  variant={rating === r ? 'default' : 'outline'}
                  data-testid={`rating-${RATING_LABEL[r].toLowerCase()}`}
                  onClick={() => setRating(r)}
                >
                  {RATING_LABEL[r]}
                </Button>
              ))}
            </div>
          )}
          {item.kind === 'short_answer' && (
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t('nextUp.shortAnswerPlaceholder')}
              data-testid="short-answer-text"
              rows={4}
            />
          )}
          {item.kind === 'teach_back' && (
            <p className="rounded bg-muted p-3 text-sm text-muted-foreground">{t('nextUp.teachBackNotice')}</p>
          )}

          {item.kind !== 'teach_back' && !graded && (
            <div className="flex flex-col gap-1.5" data-testid="confidence-control">
              <span className="text-xs text-muted-foreground">{t('nextUp.confidenceLabel')}</span>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map((c) => (
                  <Button
                    key={c}
                    type="button"
                    size="sm"
                    variant={confidence === c ? 'default' : 'outline'}
                    data-testid={`confidence-${c}`}
                    onClick={() => setConfidence(c === confidence ? null : c)}
                  >
                    {c}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-2">
            {item.kind !== 'teach_back' && !graded && (
              <Button
                data-testid="submit-answer"
                disabled={!canSubmit || submit.isPending}
                onClick={() => submit.mutate({ key: idempotencyKey, bypass: false })}
              >
                {t('nextUp.submit')}
              </Button>
            )}
            {(result || replayResult) && (
              <Button
                type="button"
                variant="outline"
                data-testid="submit-again"
                disabled={submit.isPending}
                onClick={() => submit.mutate({ key: idempotencyKey, bypass: result?.bypassed ?? false })}
              >
                {t('nextUp.submitAgain')}
              </Button>
            )}
            {!graded && (
              <Button
                type="button"
                variant="secondary"
                data-testid="just-tell-me"
                disabled={submit.isPending}
                onClick={() => submit.mutate({ key: idempotencyKey, bypass: true })}
              >
                {t('nextUp.justTellMe')}
              </Button>
            )}
            {!graded ? (
              <Button type="button" variant="ghost" data-testid="skip-for-now" onClick={handleSkip}>
                {t('nextUp.skipForNow')}
              </Button>
            ) : (
              <Button type="button" variant="ghost" data-testid="next-card" onClick={onNext}>
                {t('nextUp.nextCard')}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {submit.isError &&
        !(submit.error instanceof ApiError && submit.error.status === 409 && submit.error.code === 'idempotency_replay') && (
          <ApiStatusBanner error={submit.error} />
        )}
      {result && <ResultPanel result={result} />}
      {replayResult && <ResultPanel result={replayResult} replay />}
    </div>
  )
}

/** Local, client-only position within the current fetched batch. Keyed by
 * the batch's item ids at the call site so a genuinely new batch resets it. */
function NextBatch({ items, persona, onReload }: { items: NextItem[]; persona: Persona; onReload: () => void }) {
  const { t } = useTranslation()
  const ordered = useMemo(() => reorderBatch(items), [items])
  const [index, setIndex] = useState(0)
  const current = ordered[index]

  function move() {
    setIndex((i) => (i + 1) % ordered.length)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span data-testid="batch-position">
          {t('nextUp.cardPosition', { current: index + 1, total: ordered.length })}
        </span>
        {current.moved && <span className="italic">{t('nextUp.movedNote')}</span>}
      </div>
      <NextItemCard
        key={current.item.id}
        item={current.item}
        persona={persona}
        onSkip={move}
        onNext={index + 1 < ordered.length ? move : onReload}
      />
    </div>
  )
}

export function NextUp() {
  const { t } = useTranslation()
  const persona = usePersona()
  const queryClient = useQueryClient()
  const [batchSize, setBatchSize] = useState<number>(DEFAULT_BATCH_SIZE)
  const query = useQuery({
    queryKey: ['next-item', persona.id, batchSize],
    queryFn: () => apiFetch<NextResponse>(`/me/next?limit=${batchSize}`, { persona }),
    retry: false,
  })

  return (
    <PageScaffold title={t('nextUp.title')} description={t('nextUp.description')}>
      <div className="mb-3 flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">{t('nextUp.batchSizeLabel')}</span>
        <Select value={String(batchSize)} onValueChange={(v) => setBatchSize(Number(v))}>
          <SelectTrigger data-testid="batch-size-select" className="w-20">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {BATCH_SIZES.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">{t('nextUp.batchSizeHint', { size: batchSize })}</span>
      </div>

      <DataState<NextResponse>
        query={query}
        screen={t('nextUp.title')}
        isEmpty={(data) => data.items.length === 0}
        emptyLabel={
          query.data?.reason === 'all_mastered'
            ? t('nextUp.emptyAllMastered')
            : query.data?.reason === 'blocked_by_prerequisites'
              ? t('nextUp.emptyBlocked')
              : t('nextUp.emptyQueue')
        }
      >
        {(data) => (
          <NextBatch
            key={data.items.map((i) => i.id).join(',')}
            items={data.items}
            persona={persona}
            onReload={() => queryClient.invalidateQueries({ queryKey: ['next-item', persona.id, batchSize] })}
          />
        )}
      </DataState>
    </PageScaffold>
  )
}
