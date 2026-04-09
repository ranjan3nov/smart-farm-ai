"""
Pydantic schemas for request validation and response serialization.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inbound payload (from ESP device)
# ---------------------------------------------------------------------------


class SensorPayload(BaseModel):
    moisture_percent: float = Field(..., ge=0, le=100)
    soil_status: str
    rain_percent: float = Field(default=0.0, ge=0, le=100)
    rain_status: str
    temp_celsius: float
    humidity_percent: float = Field(..., ge=0, le=100)
    tank_status: str = Field(..., pattern="^(OK|EMPTY)$")
    tank_fill_percent: float = Field(..., ge=0, le=100)


class WeatherPayload(BaseModel):
    temp_current: float
    humidity_current: float
    precipitation_now: float = 0.0
    wind_speed: float = 0.0
    description: str = ""
    rain_probability_next_6h: float = Field(default=0.0, ge=0, le=100)
    temp_next_6h: List[float] = Field(default_factory=list)


class ContextPayload(BaseModel):
    last_pump_command: str = "OFF"
    last_pump_command_at: Optional[datetime] = None
    moisture_threshold: float = 30.0


class IrrigationRequest(BaseModel):
    """Main POST body sent by the ESP device / gateway."""

    sensor: SensorPayload
    weather: Optional[WeatherPayload] = None
    context: ContextPayload
    plant_id: Optional[int] = None  # if set, uses stored plant profile


# ---------------------------------------------------------------------------
# AI outputs
# ---------------------------------------------------------------------------


class PredictionOut(BaseModel):
    predicted_moisture_1h: float
    predicted_moisture_3h: float
    predicted_moisture_6h: float
    predicted_dry_at: Optional[datetime]
    confidence_score: float
    model_type: str

    class Config:
        from_attributes = True


class AnomalyOut(BaseModel):
    anomaly_type: str
    severity: str
    description: str

    class Config:
        from_attributes = True


class IrrigationDecisionOut(BaseModel):
    pump_command: str
    reason: str
    duration_seconds: Optional[int]

    class Config:
        from_attributes = True


class ClassificationOut(BaseModel):
    plant_name: Optional[str]
    category: Optional[str]
    moisture_min: float
    moisture_max: float
    ideal_moisture: float
    temp_min: float
    temp_max: float


# ---------------------------------------------------------------------------
# Full API response
# ---------------------------------------------------------------------------


class IrrigationResponse(BaseModel):
    pump: str
    reason: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Plant profile CRUD
# ---------------------------------------------------------------------------


class PlantProfileCreate(BaseModel):
    name: str
    category: str
    moisture_min: float = 20.0
    moisture_max: float = 80.0
    ideal_moisture: float = 50.0
    temp_min: float = 5.0
    temp_max: float = 40.0
    humidity_min: float = 30.0
    humidity_max: float = 90.0
    avg_moisture_decay_per_hour: float = 1.0
    description: Optional[str] = None


class PlantProfileOut(PlantProfileCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Historical data queries
# ---------------------------------------------------------------------------


class ReadingOut(BaseModel):
    id: int
    moisture_percent: float
    temp_celsius: float
    humidity_percent: float
    rain_percent: float
    tank_fill_percent: float
    tank_status: str
    last_pump_command: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


class TrendOut(BaseModel):
    readings: List[ReadingOut]
    avg_moisture: float
    min_moisture: float
    max_moisture: float
    total_anomalies: int
    pump_on_count: int
