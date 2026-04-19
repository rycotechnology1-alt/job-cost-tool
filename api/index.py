from __future__ import annotations

import os


if not os.environ.get("JOB_COST_API_POSTGRES_POOLED_URL"):
    os.environ["JOB_COST_API_DATABASE_PROVIDER"] = "sqlite"
    os.environ["JOB_COST_API_STORAGE_PROVIDER"] = "local"

from api.asgi import app
