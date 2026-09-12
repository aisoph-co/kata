"""Roster package (spec §Identity, roles, teams): the manager tree over
`identity.Person`, subtree resolution, the operator flag, and `focus`.
Owns `POST /admin/roster/import`.
"""

# Imported for its side effect: registers `Focus` on the shared
# `identity.models.Base` metadata, the same way `curriculum.models` does for
# its own tables.
from learning_service.roster import models as models  # noqa: F401
