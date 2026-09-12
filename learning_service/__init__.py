"""Kata learning service (spec: docs/superpowers/specs/2026-09-05-learning-
service-core-design.md in `agents-everywhere-hackathon`).

This package lands one dependency layer per Stage 0 issue (KATA-2 "C1"):
``identity``, ``roster``, and ``curriculum`` — the two leaf packages nothing
else in the core depends on — plus the app skeleton (``main``, ``db``,
``serve``) they run on. ``engine``, ``grading``, ``analytics``, ``privacy``,
and the rest of ``api`` land with the issues that depend on this one.
"""

__version__ = "1.2.1"
