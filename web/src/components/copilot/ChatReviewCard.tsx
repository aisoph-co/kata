import { CheckCircle2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { MasteryBar } from '@/components/MasteryBar'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { conceptTitle } from '@/lib/ferry-scenario'
import { RATING_LABEL, formatDateTime } from '@/lib/format'
import { CopilotReviewError, submitCopilotReview } from '@/lib/copilot-review-client'

export interface ChatReviewItem {
  id: string
  concept_id: string
  kind: 'mcq' | 'msq' | 'self_rated' | 'short_answer' | 'teach_back'
  prompt: string
  payload: { options?: string[] }
}

export interface ReviewResult {
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

/**
 * "What should I review?" (PLAN_15): the next due item as a card inside
 * the chat, recorded through the runtime's `POST /copilotkit/review` —
 * which itself is a plain passthrough to `/me/reviews`, the exact
 * grading/bypass path the Next-up screen's Submit/"Just tell me" already
 * use. This component owns no grading logic of its own.
 */
export function ChatReviewCard({
  item,
  runtimeUrl,
  headers,
}: {
  item: ChatReviewItem
  runtimeUrl: string
  headers: Record<string, string>
}) {
  const { t } = useTranslation()
  const [idempotencyKey] = useState(newIdempotencyKey)
  const [choice, setChoice] = useState('')
  const [choices, setChoices] = useState<number[]>([])
  const [rating, setRating] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [result, setResult] = useState<ReviewResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const canSubmit =
    (item.kind === 'mcq' && choice !== '') ||
    (item.kind === 'msq' && choices.length > 0) ||
    (item.kind === 'self_rated' && rating !== null) ||
    (item.kind === 'short_answer' && text.trim().length > 0)

  async function submit(bypass: boolean) {
    setPending(true)
    setError(null)
    const response = bypass
      ? {}
      : item.kind === 'mcq'
        ? { choice: Number(choice) }
        : item.kind === 'msq'
          ? { choices }
          : item.kind === 'self_rated'
            ? { rating }
            : { text }
    try {
      const data = await submitCopilotReview(runtimeUrl, headers, {
        item_id: item.id,
        idempotency_key: idempotencyKey,
        response,
        bypassed: bypass || undefined,
      })
      setResult(data)
    } catch (cause) {
      setError(cause instanceof CopilotReviewError ? cause.message : t('nextUp.reviewFailed', { defaultValue: 'Could not record that review.' }))
    } finally {
      setPending(false)
    }
  }

  const graded = result !== null

  return (
    <Card className="max-w-md" data-testid="chat-review-card">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-sm">
          <span>{item.prompt}</span>
          <Badge variant="outline">{conceptTitle(item.concept_id)}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!graded && item.kind === 'mcq' && (
          <RadioGroup value={choice} onValueChange={setChoice} data-testid="chat-mcq-options">
            {item.payload.options?.map((opt, i) => (
              <div key={i} className="flex items-center gap-2">
                <RadioGroupItem value={String(i)} id={`chat-opt-${i}`} />
                <Label htmlFor={`chat-opt-${i}`} className="font-normal">
                  {opt}
                </Label>
              </div>
            ))}
          </RadioGroup>
        )}
        {!graded && item.kind === 'msq' && (
          <div className="flex flex-col gap-2" data-testid="chat-msq-options">
            {item.payload.options?.map((opt, i) => (
              <div key={i} className="flex items-center gap-2">
                <Checkbox
                  id={`chat-chk-${i}`}
                  checked={choices.includes(i)}
                  onCheckedChange={(checked) => setChoices((prev) => (checked ? [...prev, i] : prev.filter((x) => x !== i)))}
                />
                <Label htmlFor={`chat-chk-${i}`} className="font-normal">
                  {opt}
                </Label>
              </div>
            ))}
          </div>
        )}
        {!graded && item.kind === 'self_rated' && (
          <div className="flex gap-2" data-testid="chat-self-rated-options">
            {[1, 2, 3, 4].map((r) => (
              <Button key={r} type="button" size="sm" variant={rating === r ? 'default' : 'outline'} onClick={() => setRating(r)}>
                {RATING_LABEL[r]}
              </Button>
            ))}
          </div>
        )}
        {!graded && item.kind === 'short_answer' && (
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} data-testid="chat-short-answer-text" />
        )}
        {!graded && item.kind === 'teach_back' && (
          <p className="rounded bg-muted p-2 text-xs text-muted-foreground">{t('nextUp.teachBackNotice')}</p>
        )}

        {!graded && (
          <div className="flex items-center gap-2">
            {item.kind !== 'teach_back' && (
              <Button size="sm" disabled={!canSubmit || pending} onClick={() => submit(false)} data-testid="chat-submit-answer">
                {t('nextUp.submit')}
              </Button>
            )}
            <Button size="sm" variant="secondary" disabled={pending} onClick={() => submit(true)} data-testid="chat-bypass">
              {t('nextUp.justTellMe')}
            </Button>
          </div>
        )}

        {error && <p className="text-xs text-destructive">{error}</p>}

        {result && (
          <div className="flex flex-col gap-2 border-t pt-2 text-sm" data-testid="chat-review-result">
            <div className="flex items-center gap-2">
              {result.correct ? <CheckCircle2 className="size-4 text-mastery-high" /> : <XCircle className="size-4 text-mastery-low" />}
              <span>{t('nextUp.graded')}</span>
              <Badge variant="secondary">{RATING_LABEL[result.rating] ?? result.rating}</Badge>
              {result.bypassed && <Badge variant="outline">{t('nextUp.bypassedBadge')}</Badge>}
            </div>
            {result.explanation && <p className="rounded bg-muted p-2 text-xs">{result.explanation}</p>}
            <div>
              <p className="mb-1 text-xs text-muted-foreground">{t('nextUp.resultPKnownLabel')}</p>
              <MasteryBar p={result.concept.p_known} />
            </div>
            <p className="text-xs text-muted-foreground">{t('nextUp.resultNextDueLabel')}: {formatDateTime(result.next_due_at)}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
