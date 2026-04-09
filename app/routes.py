"""
API Routes — /api/v1/irrigate endpoint only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import verify_api_key
from app.models import (
    AnomalyEvent,
    IrrigationDecision,
    MoisturePrediction,
    SensorReading,
)
from app.schemas import IrrigationRequest, IrrigationResponse, TrendOut, ReadingOut
from app.ai.classification import get_classification
from app.ai.prediction import predict_moisture
from app.ai.anomaly import detect_anomalies
from app.ai.decision import make_decision

router = APIRouter(prefix="/api/v1", tags=["Irrigation AI"])


@router.post(
    "/irrigate",
    response_model=IrrigationResponse,
    summary="Process sensor data through AI pipeline",
    dependencies=[Depends(verify_api_key)],
)
async def irrigate(payload: IrrigationRequest, db: AsyncSession = Depends(get_db)):
    """
    Full AI pipeline:
    1. Store sensor reading
    2. Classify plant
    3. Predict future moisture (regression)
    4. Detect anomalies
    5. Make irrigation decision
    6. Persist results and return enriched response
    """
    s = payload.sensor
    w = payload.weather
    ctx = payload.context

    plant_id = payload.plant_id if payload.plant_id else None

    reading = SensorReading(
        plant_id=plant_id,
        moisture_percent=s.moisture_percent,
        soil_status=s.soil_status,
        rain_percent=s.rain_percent,
        rain_status=s.rain_status,
        temp_celsius=s.temp_celsius,
        humidity_percent=s.humidity_percent,
        tank_status=s.tank_status,
        tank_fill_percent=s.tank_fill_percent,
        weather_temp_current=w.temp_current if w else None,
        weather_humidity_current=w.humidity_current if w else None,
        weather_precipitation_now=w.precipitation_now if w else None,
        weather_wind_speed=w.wind_speed if w else None,
        weather_description=w.description if w else None,
        weather_rain_prob_6h=w.rain_probability_next_6h if w else None,
        weather_temp_next_6h=w.temp_next_6h if w else None,
        last_pump_command=ctx.last_pump_command,
        last_pump_command_at=ctx.last_pump_command_at,
        moisture_threshold=ctx.moisture_threshold,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(reading)
    await db.flush()

    classification, decay_rate = await get_classification(
        db,
        plant_id,
        s.moisture_percent,
        s.temp_celsius,
        s.humidity_percent,
    )

    prediction = await predict_moisture(
        db,
        plant_id=plant_id,
        current_reading_id=reading.id,
        current_moisture=s.moisture_percent,
        decay_per_hour=decay_rate,
        rain_probability=w.rain_probability_next_6h if w else 0.0,
        rain_now=s.rain_percent,
    )

    anomalies = await detect_anomalies(
        db,
        s,
        w,
        ctx,
        classification,
        prediction,
        plant_id=plant_id,
        current_reading_id=reading.id,
    )

    decision, insights = make_decision(s, w, ctx, classification, prediction, anomalies)

    mp = MoisturePrediction(
        plant_id=plant_id,
        reading_id=reading.id,
        predicted_moisture_1h=prediction.predicted_moisture_1h,
        predicted_moisture_3h=prediction.predicted_moisture_3h,
        predicted_moisture_6h=prediction.predicted_moisture_6h,
        predicted_dry_at=prediction.predicted_dry_at,
        confidence_score=prediction.confidence_score,
        model_type=prediction.model_type,
    )
    db.add(mp)

    for a in anomalies:
        db.add(
            AnomalyEvent(
                plant_id=plant_id,
                reading_id=reading.id,
                anomaly_type=a.anomaly_type,
                severity=a.severity,
                description=a.description,
            )
        )

    db.add(
        IrrigationDecision(
            reading_id=reading.id,
            plant_id=plant_id,
            pump_command=decision.pump_command,
            reason=decision.reason,
            duration_seconds=decision.duration_seconds,
        )
    )

    await db.commit()

    return IrrigationResponse(
        pump=decision.pump_command,
        reason=decision.reason,
    )


@router.get(
    "/history",
    response_model=TrendOut,
    summary="Get sensor reading history and trend stats",
    dependencies=[Depends(verify_api_key)],
)
async def get_history(
    plant_id: Optional[int] = Query(None, description="Filter by plant ID"),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(SensorReading).order_by(desc(SensorReading.recorded_at)).limit(limit)
    if plant_id:
        query = query.where(SensorReading.plant_id == plant_id)

    result = await db.execute(query)
    readings_db = result.scalars().all()

    if not readings_db:
        return TrendOut(
            readings=[],
            avg_moisture=0,
            min_moisture=0,
            max_moisture=0,
            total_anomalies=0,
            pump_on_count=0,
        )

    moistures = [r.moisture_percent for r in readings_db]

    anomaly_q = select(func.count(AnomalyEvent.id))
    if plant_id:
        anomaly_q = anomaly_q.where(AnomalyEvent.plant_id == plant_id)
    anomaly_count = (await db.execute(anomaly_q)).scalar_one()

    pump_q = select(func.count(IrrigationDecision.id)).where(
        IrrigationDecision.pump_command == "ON"
    )
    if plant_id:
        pump_q = pump_q.where(IrrigationDecision.plant_id == plant_id)
    pump_on_count = (await db.execute(pump_q)).scalar_one()

    readings_out = [
        ReadingOut(
            id=r.id,
            moisture_percent=r.moisture_percent,
            temp_celsius=r.temp_celsius,
            humidity_percent=r.humidity_percent,
            rain_percent=r.rain_percent,
            tank_fill_percent=r.tank_fill_percent,
            tank_status=r.tank_status,
            last_pump_command=r.last_pump_command,
            recorded_at=r.recorded_at,
        )
        for r in readings_db
    ]

    return TrendOut(
        readings=readings_out,
        avg_moisture=round(sum(moistures) / len(moistures), 2),
        min_moisture=round(min(moistures), 2),
        max_moisture=round(max(moistures), 2),
        total_anomalies=anomaly_count,
        pump_on_count=pump_on_count,
    )
