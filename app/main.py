from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.certificates import router as certificates_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import logger
from app.services.worker import recover_interrupted_jobs

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown events."""
    logger.info("Application startup: Recovering interrupted jobs if any...")
    try:
        recover_interrupted_jobs()
    except Exception as e:
        logger.error(f"Error during startup job recovery: {e}")
    yield
    logger.info("Application shutdown: Cleaning up resources.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Bulk Certificate Generator API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Register global exception handlers for uniform JSON error responses
register_exception_handlers(app)

# Include API routers
app.include_router(health_router)
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(certificates_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs": "/docs",
        "api_v1": "/api/v1",
    }
