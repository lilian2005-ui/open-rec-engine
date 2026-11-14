"""FastAPI application entry-point."""

from fastapi import FastAPI

from backend.api.routes.auth import router as auth_router

app = FastAPI(title="Open Rec")

app.include_router(auth_router)