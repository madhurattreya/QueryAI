from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import backend.config as config
from backend.services.forecasting import ForecastingService

router = APIRouter(prefix="/api")

class ForecastRequest(BaseModel):
    dataset_name: str
    date_column: str
    value_column: str
    periods: int = 3
    freq: str = "ME"

class WhatIfRequest(BaseModel):
    dataset_name: str
    target_column: str
    increase_percentage: float

@router.post("/forecasting/trend")
def run_linear_trend_endpoint(req: ForecastRequest):
    try:
        df = config.datasets.get(req.dataset_name)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="Dataset not found or empty.")
            
        service = ForecastingService()
        res_df = service.forecast_linear_trend(df, req.date_column, req.value_column, req.periods, req.freq)
        return {"status": "success", "result": res_df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/forecasting/smoothing")
def run_exp_smoothing_endpoint(req: ForecastRequest):
    try:
        df = config.datasets.get(req.dataset_name)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="Dataset not found or empty.")
            
        service = ForecastingService()
        res_df = service.forecast_exponential_smoothing(df, req.date_column, req.value_column, req.periods, req.freq)
        return {"status": "success", "result": res_df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/forecasting/what-if")
def run_what_if_endpoint(req: WhatIfRequest):
    try:
        df = config.datasets.get(req.dataset_name)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="Dataset not found or empty.")
            
        service = ForecastingService()
        res_df = service.scenario_what_if(df, req.target_column, req.increase_percentage)
        return {"status": "success", "result": res_df.head(100).to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
