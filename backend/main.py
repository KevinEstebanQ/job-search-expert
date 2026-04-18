import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from backend.db.schema import init_db
from backend.api.ai import router as ai_router
from backend.api.applications import router as applications_router
from backend.api.jobs import router as jobs_router
from backend.api.profile import router as profile_router
from backend.api.scrape import router as scrape_router
from backend.api.stats import router as stats_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Job Search Expert API",
    description="Self-hosted job search assistant backed by Claude agents.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai_router)
app.include_router(applications_router)
app.include_router(jobs_router)
app.include_router(profile_router)
app.include_router(scrape_router)
app.include_router(stats_router)


@app.get("/health")
def health():
    return {"status": "ok"}
