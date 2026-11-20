"""FastAPI application entry-point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.auth import router as auth_router
from backend.api.routes.drafts import router as drafts_router
from backend.api.routes.jobs import router as jobs_router
from backend.api.routes.leads import router as leads_router
from backend.api.routes.pipeline import router as pipeline_router
from backend.api.routes.settings import router as settings_router
from backend.config import settings
from backend.pipeline import schedule


@asynccontextmanager
async def lifespan(app: FastAPI):
    """P1-7: the scheduled-run timer (every 15 minutes) lives as long as the server.
    TestClient(app) without ``with`` does not run this, so tests never start it."""
    scheduler = schedule.start_scheduler()
    yield
    scheduler.shutdown()
    schedule.log.info("Scheduler stopped")


app = FastAPI(title="Open Rec", lifespan=lifespan)

# Only the frontend address(es) from settings may call the API. Never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(leads_router)
app.include_router(drafts_router)
app.include_router(settings_router)
app.include_router(pipeline_router)
