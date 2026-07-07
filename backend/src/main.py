from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.environments import router as environments_router
from backend.src.api.ingestion import router as ingestion_router
from backend.src.api.plans import router as plans_router
from backend.src.api.tests import router as tests_router
from backend.src.api.upload import router as upload_router
from backend.src.config import settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", service=settings.service_name, embedding_dim=settings.embedding_dim)
    yield
    log.info("shutdown")


app = FastAPI(
    title="AI Test Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(plans_router, prefix="/api/v1")
app.include_router(environments_router, prefix="/api/v1")
app.include_router(tests_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.service_name}
