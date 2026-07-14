from fastapi import APIRouter
from backend.services.logger import get_telemetry_stats

router = APIRouter(prefix="/api")

@router.get("/observability/stats")
def get_stats():
    """
    Returns aggregated telemetry statistics for the observability dashboard.
    """
    from backend.services.telemetry import TelemetryService
    return TelemetryService().get_aggregated_telemetry()
