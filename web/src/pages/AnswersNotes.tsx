import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DataState } from '@/components/DataState'
import { PageScaffold } from '@/components/PageScaffold'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { useApiQuery } from '@/hooks/useApiQuery'
import { apiFetch, ApiError } from '@/lib/api-client'
import { errorExplanation } from '@/lib/error-explanations'
import { formatDateTime } from '@/lib/format'
import { usePersona } from '@/lib/persona-store'

interface Answer {
  id: string
  review_id: string
  text: string
  created_at: string
}

interface Note {
  id: string
  text: string
  created_at: string
  updated_at: string
}

function AnswersSection() {
  const { t } = useTranslation()
  const persona = usePersona()
  const queryClient = useQueryClient()
  const answers = useApiQuery<{ answers: Answer[] }>('answers', '/me/answers')

  const deleteAll = useMutation({
    mutationFn: () => apiFetch('/me/answers', { persona, method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['answers', persona.id] }),
  })

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">{t('answersNotes.answersTitle')}</CardTitle>
        <Button
          size="sm"
          variant="outline"
          disabled={deleteAll.isPending || answers.data?.answers.length === 0}
          onClick={() => deleteAll.mutate()}
        >
          {t('answersNotes.deleteAll')}
        </Button>
      </CardHeader>
      <CardContent>
        <DataState
          query={answers}
          screen={t('answersNotes.answersTitle')}
          isEmpty={(d) => d.answers.length === 0}
          emptyLabel={t('answersNotes.emptyAnswers')}
        >
          {(d) => (
            <ul className="flex flex-col gap-2 text-sm">
              {d.answers.map((a) => (
                <li key={a.id} className="rounded border p-2">
                  <p>{a.text}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(a.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
        </DataState>
      </CardContent>
    </Card>
  )
}

function NotesSection() {
  const { t } = useTranslation()
  const persona = usePersona()
  const queryClient = useQueryClient()
  const notes = useApiQuery<{ notes: Note[] }>('notes', '/me/notes')
  const [text, setText] = useState('')

  const addNote = useMutation({
    mutationFn: () => apiFetch<Note>('/me/notes', { persona, method: 'POST', body: { text } }),
    onSuccess: () => {
      setText('')
      queryClient.invalidateQueries({ queryKey: ['notes', persona.id] })
    },
  })

  const deleteNote = useMutation({
    mutationFn: (id: string) => apiFetch(`/me/notes/${id}`, { persona, method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notes', persona.id] }),
  })

  const addNoteError = addNote.error
  const addNoteCode = addNoteError instanceof ApiError ? addNoteError.code : undefined
  const addNoteMessage = addNoteError instanceof ApiError ? addNoteError.message : String(addNoteError ?? '')
  const explanation = errorExplanation(addNoteCode)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('answersNotes.notesTitle')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t('answersNotes.addNotePlaceholder')}
            rows={3}
          />
          <div className="flex items-center gap-2">
            <Button size="sm" disabled={!text.trim() || addNote.isPending} onClick={() => addNote.mutate()}>
              {t('answersNotes.addNote')}
            </Button>
            {addNote.isError && (
              <span className="text-xs text-destructive">
                {addNoteCode && <span className="mr-1 font-mono">{addNoteCode}</span>}
                {addNoteMessage}
                {explanation && <span className="ml-1 text-destructive/70">· {explanation}</span>}
              </span>
            )}
          </div>
        </div>
        <DataState
          query={notes}
          screen={t('answersNotes.notesTitle')}
          isEmpty={(d) => d.notes.length === 0}
          emptyLabel={t('answersNotes.emptyNotes')}
        >
          {(d) => (
            <ul className="flex flex-col gap-2 text-sm">
              {d.notes.map((n) => (
                <li key={n.id} className="flex items-start justify-between gap-2 rounded border p-2">
                  <div>
                    <p>{n.text}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(n.created_at)}</p>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={t('answersNotes.deleteNoteAria')}
                    onClick={() => deleteNote.mutate(n.id)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </DataState>
      </CardContent>
    </Card>
  )
}

export function AnswersNotes() {
  const { t } = useTranslation()
  return (
    <PageScaffold title={t('answersNotes.title')} description={t('answersNotes.description')}>
      <div className="flex flex-col gap-6">
        <AnswersSection />
        <NotesSection />
      </div>
    </PageScaffold>
  )
}
