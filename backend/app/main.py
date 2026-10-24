"""FastAPI application entry point for GlucoTwin AI.

Run from the project root (Windows):

    .venv\\Scripts\\python -m uvicorn backend.app.main:app --reload --port 8000

Interactive API docs: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .api.auth_routes import router as auth_router
from .api.routes import router
from .ml.infer import Forecaster, MetricsNotAvailableError, ModelNotAvailableError
from .services.auth import AuthService
from .services.repository import (
    DataRepository,
    DataValidationError,
    DuplicatePatientError,
    PatientNotFoundError,
)
from .services.risk import load_thresholds
from .services.twin import DigitalTwinEngine


class AppState:
    """Lazily-constructed shared services with clear error surfacing."""

    def __init__(self, forecaster: Forecaster | None = None):
        self.forecaster = forecaster or Forecaster()
        self._repo: DataRepository | None = None
        self._twin: DigitalTwinEngine | None = None
        self._auth: AuthService | None = None
        self._data_error: Exception | None = None
        self.thresholds = load_thresholds()

    @property
    def repo(self) -> DataRepository:
        if self._repo is None:
            if self._data_error is not None:
                raise self._data_error
            try:
                self._repo = DataRepository()
            except Exception as exc:
                self._data_error = exc
                raise
        return self._repo

    @property
    def twin(self) -> DigitalTwinEngine:
        if self._twin is None:
            self._twin = DigitalTwinEngine(
                self.repo, self.forecaster, thresholds=self.thresholds
            )
        return self._twin

    @property
    def auth(self) -> AuthService:
        if self._auth is None:
            self._auth = AuthService(self.repo.db)
        return self._auth


def create_app(state: AppState | None = None) -> FastAPI:
    app = FastAPI(
        title=config.API_TITLE,
        version=config.API_VERSION,
        description=(
            "GlucoTwin AI - a digital twin proof-of-concept that forecasts a synthetic "
            "patient's glucose trajectory and flags potential threshold violations. "
            "Educational prototype only; NOT a medical device."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state = state or AppState()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(auth_router)

    @app.exception_handler(PatientNotFoundError)
    async def patient_not_found_handler(request: Request, exc: PatientNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DuplicatePatientError)
    async def duplicate_patient_handler(request: Request, exc: DuplicatePatientError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ModelNotAvailableError)
    async def model_unavailable_handler(request: Request, exc: ModelNotAvailableError):
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc), "remedy": "python -m backend.scripts.train_model"},
        )

    @app.exception_handler(MetricsNotAvailableError)
    async def metrics_unavailable_handler(request: Request, exc: MetricsNotAvailableError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(DataValidationError)
    async def data_error_handler(request: Request, exc: DataValidationError):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.get("/", include_in_schema=False)
    def root():
        return {
            "service": config.API_TITLE,
            "message": "Digital twin API for synthetic diabetes risk monitoring.",
            "docs": "/docs",
            "health": "/api/health",
            "disclaimer": "Synthetic demo data only - not a medical device.",
        }

    return app


app = create_app()