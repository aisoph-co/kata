"""The learning engine (spec §Learning engine): the append-only `review` log
and the two derived caches rebuilt from it, `card_state` (FSRS-6) and
`concept_state` (BKT) — plus next-item selection and replay, both pure
functions of that log so a rebuild is byte-identical to live state
(spec §Architecture, invariant 2).

`focus` also lives here (`models.Focus`), not in `roster`, where the design
spec's own package table puts it: `roster`/`identity`/`curriculum` are
KATA-2's own package (still under review when this issue was dispatched —
see the Epic's dispatch comment), and `focus` is read by nothing but this
package's next-item selection and the `team` surface this issue also owns,
so keeping it here avoids touching those files at all.
"""

from __future__ import annotations
