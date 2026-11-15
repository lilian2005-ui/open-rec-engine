"""FastAPI application entry-point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.auth import router as auth_router
from backend.api.routes.drafts import router as drafts_router
from backend.api.routes.jobs import router as jobs_router
from backend.api.routes.leads import router as leads_router
from backend.api.routes.settings import router as settings_router

app = FastAPI(title="Open Rec")

# The frontend dev server (Vite). The token travels in the Authorization header.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(leads_router)
app.include_router(drafts_router)
app.include_router(settings_router)
