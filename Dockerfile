# Kata learning service (spec §Deployment; KATA-4). Builds `learning`,
# `learning-retention`, `learning-replay` — one image, three Railway
# services distinguished only by their start command (`deploy/kata/README.md`
# "Topology"; `RUNBOOK.md` "Deploy commands" — all three `railway up` from a
# `kata` checkout, this repo's root as the build context).
#
# Required at runtime: DATABASE_URL, SERVICE_TOKEN, WEB_SERVICE_TOKEN,
# OPENROUTER_API_KEY (unset only fails a short_answer/teach_back grading
# call, per `main.py`'s `_build_llm_client`, never startup). `PORT` defaults
# to 8000 (`serve.py`). `LEARNING_SEED=ferry` loads the golden scenario once
# on boot (`learning_service/seed.py`), idempotent across restarts.
FROM python:3.13-slim

WORKDIR /app

# Build deps only for asyncpg's C extension; removed from the final layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# The rest of this monorepo: `plugins/hermes-kata` so
# `roster.service.plan_digest_jobs_count` can reach `hermes_kata.digests`
# (best-effort — see that module's own docstring), and `learning_service/`
# itself, seed data included.
COPY . .

ENV PORT=8000
EXPOSE 8000

# No migration step: the app creates its own schema on boot
# (`main.py`'s lifespan runs `Base.metadata.create_all`, idempotent across
# restarts). The two cron services override this with their own start
# command (`python -m learning_service.cli retention|replay`).
CMD ["python", "-m", "learning_service.serve"]
