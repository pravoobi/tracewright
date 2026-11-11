import asyncio
import sys
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

if sys.platform == "win32":
    # Playwright's async API launches its browser as a subprocess, which
    # asyncio's SelectorEventLoop cannot do on Windows (raises
    # NotImplementedError from _make_subprocess_transport). This is why
    # Generator Phase 1 (build_app_model) had only ever run via standalone
    # scripts before this line existed -- never inside the actual server.
    #
    # NOTE: this only takes effect when uvicorn is run WITHOUT --reload
    # (scripts/run-backend-no-reload.sh). Confirmed by direct testing:
    # identical code, --reload's multiprocessing worker on Windows resets
    # the policy back to Selector regardless of this line, while a plain
    # `uvicorn backend.src.main:app` respects it and gets ProactorEventLoop.
    # Everything else works fine under --reload; only the Generator's
    # build-registry endpoint (real Playwright browser launch) needs this.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.src.api.auth import router as auth_router
from backend.src.api.environments import router as environments_router
from backend.src.api.generator import router as generator_router
from backend.src.api.ingestion import router as ingestion_router
from backend.src.api.metrics import router as metrics_router
from backend.src.api.plans import router as plans_router
from backend.src.api.tests import router as tests_router
from backend.src.api.upload import router as upload_router
from backend.src.config import settings
from backend.src.llm.cost import TenantBudgetExceededError

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", service=settings.service_name, embedding_dim=settings.embedding_dim)
    yield
    log.info("shutdown")


app = FastAPI(
    title="Tracewright",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """The upload handler's byte-count limit only runs AFTER the framework has
    already spooled the whole multipart body to disk. Reject on the declared
    Content-Length first so an oversized upload is refused before it is read.
    (A chunked request with no Content-Length can still bypass this; a
    reverse proxy body-size limit is the complete fix for that case.)"""
    if request.method == "POST" and request.url.path.startswith("/api/v1/upload/"):
        declared = request.headers.get("content-length")
        # Multipart framing adds a little overhead over the file itself.
        if declared and declared.isdigit() and int(declared) > settings.max_upload_size_bytes + 1_048_576:
            return JSONResponse(status_code=413, content={"detail": "Upload exceeds maximum size"})
    return await call_next(request)


@app.exception_handler(TenantBudgetExceededError)
async def tenant_budget_exceeded_handler(request: Request, exc: TenantBudgetExceededError):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


app.include_router(auth_router, prefix="/api/v1")
app.include_router(upload_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(plans_router, prefix="/api/v1")
app.include_router(environments_router, prefix="/api/v1")
app.include_router(tests_router, prefix="/api/v1")
app.include_router(generator_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.service_name}
