"""Creates the demo database's schema, the same way the app does on boot.

`main.py`'s lifespan runs `Base.metadata.create_all` for a configured
`DATABASE_URL`; this package has no migration chain. The demo runner seeds
before the API starts, so it needs the tables first — hence this standalone
copy of that one step. Idempotent: only creates tables that don't exist.

The three `models` imports are side effects, not usage: each registers its
tables on the shared `Base.metadata` before `create_all` reads it.
"""

import asyncio

from learning_service.db import session_scope
from learning_service.identity.models import Base
from learning_service.curriculum import models as _curriculum_models  # noqa: F401
from learning_service.engine import models as _engine_models  # noqa: F401
from learning_service.privacy import models as _privacy_models  # noqa: F401


async def main() -> None:
    async with session_scope() as session:
        conn = await session.connection()
        await conn.run_sync(Base.metadata.create_all)
        # PostgreSQL makes DDL transactional; persist before the seed opens
        # its own session.
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
