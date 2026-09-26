from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from storm_nowcast.alerts.engine import AlertEngine, AlertRule
from storm_nowcast.api.dependencies import EventDataUnavailable, load_analysis_service, optional_catalog
from storm_nowcast.config import PROJECT_ROOT, Settings, load_settings
from storm_nowcast.data.sources import (
    CmorphSource,
    ImdLightningSource,
    ImdRadarSource,
    ImdStationSource,
    MosdacSatelliteSource,
)
from storm_nowcast.evaluation import evaluate_forecasts
from storm_nowcast.services.analysis import AnalysisService, AnalysisSnapshot


def create_app(
    *,
    settings: Settings | None = None,
    catalog_path: Path | None = None,
    service_override: AnalysisService | None = None,
) -> FastAPI:
    configured = settings or load_settings()
    catalog_file = catalog_path or PROJECT_ROOT / "configs" / "events.yaml"
    catalog = optional_catalog(catalog_file)
    cached_service: AnalysisService | None = service_override

    application = FastAPI(
        title="StormNowcast read-only API",
        version="0.2.0",
        description="Read-only access to the scientifically qualified StormNowcast analysis services.",
    )

    def service() -> AnalysisService:
        nonlocal cached_service
        if cached_service is None:
            try:
                cached_service = load_analysis_service(configured, catalog)
            except EventDataUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        return cached_service

    def snapshot(frame: int | None, target_lat: float, target_lon: float) -> AnalysisSnapshot:
        current = service()
        selected = current.player.frame_count - 1 if frame is None else frame
        try:
            return current.snapshot(frame_index=selected, target=(target_lat, target_lon))
        except IndexError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.get("/health")
    def health() -> dict:
        ready = service_override is not None or configured.data.processed_event.exists()
        return {
            "status": "ok",
            "event_data": "ready" if ready else "missing",
            "mode": "read-only",
        }

    @application.get("/sources")
    def sources() -> list[dict]:
        adapters = (
            CmorphSource(),
            MosdacSatelliteSource(),
            ImdRadarSource(),
            ImdLightningSource(),
            ImdStationSource(),
        )
        return [adapter.status().model_dump(mode="json") for adapter in adapters]

    @application.get("/events")
    def events() -> list[dict]:
        return [event.model_dump(mode="json") for event in catalog.events]

    @application.get("/storms")
    def storms(
        frame: int | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> list[dict]:
        return [item.model_dump(mode="json") for item in snapshot(frame, target_lat, target_lon).tracks]

    @application.get("/storms/{storm_id}")
    def storm(
        storm_id: str,
        frame: int | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> dict:
        for item in snapshot(frame, target_lat, target_lon).tracks:
            if item.id == storm_id:
                return item.model_dump(mode="json")
        raise HTTPException(status_code=404, detail=f"Unknown active storm: {storm_id}")

    @application.get("/nowcast")
    def nowcast(
        frame: int | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> dict:
        return snapshot(frame, target_lat, target_lon).model_dump(mode="json")

    @application.get("/hazards")
    def hazards(
        frame: int | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> dict[str, list[dict]]:
        current = snapshot(frame, target_lat, target_lon)
        return {track.id: [item.model_dump(mode="json") for item in track.hazards] for track in current.tracks}

    @application.get("/alerts")
    def alerts(
        frame: int | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> list[dict]:
        current = snapshot(frame, target_lat, target_lon)
        engine = AlertEngine(
            [
                AlertRule(
                    rule_id="prototype-extreme-rain-near-target",
                    hazard="EXTREME_RAIN",
                    risk_levels={"HIGH", "VERY HIGH"},
                    minimum_confidence="MODERATE",
                )
            ]
        )
        emitted = []
        for track in current.tracks:
            emitted.extend(
                engine.evaluate(
                    track_id=track.id,
                    target=f"{target_lat:.4f},{target_lon:.4f}",
                    source_timestamp=current.observation_time,
                    hazards=track.hazards,
                    eta=track.eta,
                    confidence=track.confidence.label,
                )
            )
        return [item.model_dump(mode="json") for item in emitted]

    @application.get("/evaluation")
    def evaluation(
        frame: int | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> list[dict]:
        current_service = service()
        selected = current_service.player.frame_count - 1 if frame is None else frame
        replay = current_service.player.analyze(selected, (target_lat, target_lon))
        metrics = evaluate_forecasts(replay.tracks, current_service.player.all_tracks())
        return [item.model_dump(mode="json") for item in metrics]

    return application


app = create_app()
