"""FastAPI application entry point for Hishabi.

Complies with PROJECT_RULES.md.
"""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import router as auth_router
from app.api.v1.categories import router as categories_router
from app.api.v1.products import router as products_router
from app.api.v1.users import router as users_router
from app.core.config import settings

app = FastAPI(
    title="Hishabi API",
    version="1.0.0",
    description="Backend API for Hishabi inventory and business management.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global Exception Handlers (PROJECT_RULES.md Error Shape)
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Ensure HTTP exceptions adhere to {"error": {"code": ..., "message": ...}}."""
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Ensure validation errors adhere to standard error shape."""
    first_error = exc.errors()[0] if exc.errors() else {}
    msg = first_error.get("msg", "Validation error")
    loc = " -> ".join(str(l) for l in first_error.get("loc", []))
    detail_msg = f"{loc}: {msg}" if loc else msg
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": "VALIDATION_ERROR", "message": detail_msg}},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(categories_router)
app.include_router(products_router)


# ---------------------------------------------------------------------------
# Health / Root Endpoints
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"])
def root():
    return {
        "status": "online",
        "app": "Hishabi API",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "healthy"}

