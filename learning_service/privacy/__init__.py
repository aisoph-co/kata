"""Privacy and retention (spec §Privacy and retention): `answer` storage
(learner-only, 90-day retention), `learner_note` (20-note/500-char caps),
and the `/team/*` `audit` log. Nothing here is ever joined by an analytics,
manager, or admin query.
"""

from __future__ import annotations
