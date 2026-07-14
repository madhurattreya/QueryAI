from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import backend.config as config
from backend.services.loader import load_default_datasets
from backend.routers.settings import router as settings_router
from backend.routers.upload import router as upload_router
from backend.routers.sql import router as sql_router
from backend.routers.query import router as query_router
from backend.routers.insights import router as insights_router
from backend.routers.observability import router as observability_router
from backend.routers.datasets import router as datasets_router
from backend.routers.relationships import router as relationships_router
from backend.routers.semantic_model import router as semantic_model_router
from backend.routers.dashboards import router as dashboards_router
from backend.routers.scheduler import router as scheduler_router
from backend.routers.alerts import router as alerts_router
from backend.routers.forecasting import router as forecasting_router
from backend.routers.security import router as security_router
from backend.routers.collaboration import router as collaboration_router
from backend.routers.search import router as search_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the active dataset on startup from the registry
    from backend.services.dataset_manager import DatasetManager
    from backend.services.scheduler import SchedulerService
    try:
        DatasetManager().load_active_dataset_on_startup()
    except Exception:
        pass
    try:
        SchedulerService().start_scheduler()
    except Exception:
        pass
    try:
        from backend.services.alert_engine import AlertEngine
        AlertEngine().start_monitoring()
    except Exception:
        pass
    yield

app = FastAPI(
    title="QueryIQ",
    lifespan=lifespan
)

# Setup restricted CORS
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(settings_router)
app.include_router(upload_router)
app.include_router(sql_router)
app.include_router(query_router)
app.include_router(insights_router)
app.include_router(observability_router)
app.include_router(datasets_router)
app.include_router(relationships_router)
app.include_router(semantic_model_router)
app.include_router(dashboards_router)
app.include_router(scheduler_router)
app.include_router(alerts_router)
app.include_router(forecasting_router)
app.include_router(security_router)
app.include_router(collaboration_router)
app.include_router(search_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to QueryIQ"}
