"""Answer/note/audit persistence (spec §Privacy and retention). 90-day
answer retention is enforced two ways: inline, by purging expired rows
before every `/me/answers` read or delete (so a stale row never leaks even
if the nightly cron missed a run), and by the nightly `learning_service.cli
retention` job (spec §Deployment).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.engine.models import ANSWER_RETENTION_DAYS, NOTE_MAX_CHARS, NOTE_MAX_COUNT
from learning_service.privacy.models import Answer, AuditEntry, LearnerNote


class NoteCapExceeded(Exception):
    """More than `NOTE_MAX_COUNT` notes, or a note over `NOTE_MAX_CHARS`."""


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


async def purge_expired_answers(session: AsyncSession) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ANSWER_RETENTION_DAYS)
    await session.execute(delete(Answer).where(Answer.created_at < cutoff))
    await session.commit()


async def list_answers(session: AsyncSession, person_id: str) -> list[Answer]:
    result = await session.execute(
        select(Answer).where(Answer.person_id == person_id).order_by(Answer.created_at.desc(), Answer.id.desc())
    )
    return list(result.scalars().all())


async def delete_answers(session: AsyncSession, person_id: str) -> None:
    await session.execute(delete(Answer).where(Answer.person_id == person_id))
    await session.commit()


# ---------------------------------------------------------------------------
# Learner notes
# ---------------------------------------------------------------------------


async def list_notes(session: AsyncSession, person_id: str) -> list[LearnerNote]:
    result = await session.execute(
        select(LearnerNote)
        .where(LearnerNote.person_id == person_id)
        .order_by(LearnerNote.created_at.desc(), LearnerNote.id.desc())
    )
    return list(result.scalars().all())


async def create_note(session: AsyncSession, *, person_id: str, text: str) -> LearnerNote:
    if len(text) > NOTE_MAX_CHARS:
        raise NoteCapExceeded(f"note exceeds {NOTE_MAX_CHARS} characters")
    count = await session.execute(select(LearnerNote.id).where(LearnerNote.person_id == person_id))
    if len(count.all()) >= NOTE_MAX_COUNT:
        raise NoteCapExceeded(f"at most {NOTE_MAX_COUNT} notes per person")
    note = LearnerNote(person_id=person_id, text=text)
    session.add(note)
    await session.commit()
    return note


async def delete_note(session: AsyncSession, *, person_id: str, note_id: str) -> bool:
    note = await session.get(LearnerNote, note_id)
    if note is None or note.person_id != person_id:
        return False
    await session.delete(note)
    await session.commit()
    return True


async def delete_notes(session: AsyncSession, person_id: str) -> None:
    await session.execute(delete(LearnerNote).where(LearnerNote.person_id == person_id))
    await session.commit()


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


async def write_audit(session: AsyncSession, *, actor_person_id: str, subject_scope: str, endpoint: str) -> None:
    session.add(AuditEntry(actor_person_id=actor_person_id, subject_scope=subject_scope, endpoint=endpoint))
    await session.commit()


async def list_audit_for(session: AsyncSession, actor_ids: list[str]) -> list[AuditEntry]:
    result = await session.execute(
        select(AuditEntry).where(AuditEntry.actor_person_id.in_(actor_ids)).order_by(AuditEntry.at.desc())
    )
    return list(result.scalars().all())
