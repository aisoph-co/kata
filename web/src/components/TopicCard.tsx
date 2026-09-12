import { useState } from 'react'
import { CitationChip } from '@/components/CitationChip'
import { ExcerptPanel } from '@/components/ExcerptPanel'
import { ROLE_LABEL, type Topic } from '@/lib/connections-model'

/**
 * One persona topic card (SCREENS.md #02: "three persona topic cards, each
 * citing issue ids and a thread"). `isOwnTopic` highlights the signed-in
 * learner's own role's card ("the learner's own topic highlighted").
 */
export function TopicCard({ topic, isOwnTopic }: { topic: Topic; isOwnTopic: boolean }) {
  const [openCitation, setOpenCitation] = useState<string | null>(null)

  return (
    <article
      className={`topic-card${isOwnTopic ? ' topic-card--own' : ''}`}
      data-testid="persona-topic-card"
      aria-label={topic.title}
    >
      <div className="topic-card-header">
        <span className="badge badge--slate">{ROLE_LABEL[topic.persona_role] ?? topic.persona_role}</span>
        {isOwnTopic && <span className="badge badge--cyan">Your topic</span>}
      </div>
      <h3 className="topic-card-title">{topic.title}</h3>
      {topic.description && <p className="topic-card-description">{topic.description}</p>}
      <ul className="citation-list">
        {topic.grounded_in.map((citation) => (
          <li key={citation}>
            <CitationChip
              citation={citation}
              isOpen={openCitation === citation}
              onToggle={(next) => setOpenCitation((current) => (current === next ? null : next))}
            />
            {openCitation === citation && <ExcerptPanel citation={citation} />}
          </li>
        ))}
      </ul>
    </article>
  )
}
