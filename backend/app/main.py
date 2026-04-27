"""FastAPI backend application setup."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

os.environ.setdefault("BACKEND_DB_PATH", "./data/backend.db")
os.environ.setdefault(
    "AI_SYSTEM_URL",
    "http://ai_system:8000"
    if Path("/.dockerenv").exists()
    else "http://localhost:8000",
)
os.environ.setdefault("AI_SYSTEM_TIMEOUT_SECONDS", "90")

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.market import router as market_router
from app.api.portfolio import router as portfolio_router
from app.api.sar import router as sar_router
from app.api.search import router as search_router
from app.api.system import router as system_router
from app.api.transactions import router as transactions_router
from app.db import init_db


app = FastAPI(title="FinGuard Backend")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:13000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.exception_handler(HTTPException)
def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        content = exc.detail
    else:
        content = {"error": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=content)


app.include_router(system_router)
app.include_router(auth_router)
app.include_router(audit_router)
app.include_router(cases_router)
app.include_router(portfolio_router)
app.include_router(transactions_router)
app.include_router(market_router)
app.include_router(sar_router)
app.include_router(search_router)
