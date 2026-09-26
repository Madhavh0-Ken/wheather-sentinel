from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from storm_nowcast.alerts.engine import AlertEngine, AlertRule
from storm_nowcast.api.dependencies import (
    EventDataUnavailable,
    load_analysis_service,
    load_repository_analysis_service,
    optional_catalog,
    repository_event_identity,
)
from storm_nowcast.config import PROJECT_ROOT, Settings, load_settings
from storm_nowcast.data.cmorph_cache import CmorphCache
from storm_nowcast.data.sources import (
    CmorphSource,
    ImdLightningSource,
    ImdRadarSource,
    ImdStationSource,
    MosdacSatelliteSource,
)
from storm_nowcast.evaluation import evaluate_forecasts
from storm_nowcast.events.builder import CmorphEventBuilder
from storm_nowcast.events.custom import CustomEventRequest
from storm_nowcast.events.errors import EventErrorCode, EventOperationError
from storm_nowcast.events.repository import EventRepository
from storm_nowcast.services.analysis import AnalysisService, AnalysisSnapshot


def create_app(
    *,
    settings: Settings | None = None,
    catalog_path: Path | None = None,
    service_override: AnalysisService | None = None,
    repository_override: EventRepository | None = None,
    builder_override: CmorphEventBuilder | None = None,
) -> FastAPI:
    configured = settings or load_settings()
    catalog_file = catalog_path or PROJECT_ROOT / "configs" / "events.yaml"
    catalog = optional_catalog(catalog_file)
    repository = repository_override or EventRepository(
        catalog_file, PROJECT_ROOT / "data" / "events" / "custom"
    )
    builder = builder_override or CmorphEventBuilder(
        repository,
        CmorphCache(PROJECT_ROOT / "data" / "raw" / "cmorph"),
        configured,
    )
    default_service: AnalysisService | None = service_override
    selected_services: dict[tuple[str, str], AnalysisService] = {}

    application = FastAPI(
        title="StormNowcast read-only API",
        version="0.2.0",
        description="Read-only access to the scientifically qualified StormNowcast analysis services.",
    )

    status_by_code = {
        EventErrorCode.INVALID_BOUNDS: 422,
        EventErrorCode.REGION_TOO_LARGE: 422,
        EventErrorCode.OUTSIDE_CMORPH_COVERAGE: 422,
        EventErrorCode.DATELINE_CROSSING: 422,
        EventErrorCode.INVALID_TIME_WINDOW: 422,
        EventErrorCode.UNSUPPORTED_ARCHIVE_DATE: 422,
        EventErrorCode.EVENT_BUILD_IN_PROGRESS: 409,
        EventErrorCode.NOAA_UNAVAILABLE: 503,
        EventErrorCode.NOAA_FILE_CORRUPT: 502,
        EventErrorCode.CACHED_EVENT_INVALID: 409,
        EventErrorCode.EVENT_NOT_FOUND: 404,
        EventErrorCode.BUILTIN_EVENT_PROTECTED: 409,
        EventErrorCode.UNSAFE_EVENT_PATH: 409,
        EventErrorCode.EVENT_STORAGE_FAILED: 507,
    }

    @application.exception_handler(EventOperationError)
    async def event_error_handler(_request: Request, exc: EventOperationError) -> JSONResponse:
        return JSONResponse(status_code=status_by_code[exc.code], content=exc.as_dict())

    def service(event_id: str | None = None) -> AnalysisService:
        nonlocal default_service
        if event_id is None:
            if default_service is not None:
                return default_service
            try:
                default_service = load_analysis_service(configured, catalog)
            except EventDataUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            return default_service
        if service_override is not None and event_id == service_override.event_id:
            return service_override
        try:
            _, checksum = repository_event_identity(repository, event_id)
            key = (event_id, checksum)
            if key not in selected_services:
                selected_services[key] = load_repository_analysis_service(
                    configured, repository, event_id
                )[0]
            return selected_services[key]
        except EventDataUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def snapshot(
        frame: int | None,
        target_lat: float,
        target_lon: float,
        event_id: str | None = None,
    ) -> AnalysisSnapshot:
        current = service(event_id)
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
        return [event.model_dump(mode="json") for event in repository.list_events()]

    @application.post("/events/prepare")
    def prepare_event(request: CustomEventRequest) -> dict:
        prepared = builder.prepare(request)
        selected_services.pop(
            (prepared.manifest.event_id, prepared.manifest.event_sha256), None
        )
        return {
            "created": prepared.created,
            "reused": prepared.reused,
            "analysis_ready": prepared.manifest.analysis_ready,
            "manifest": prepared.manifest.model_dump(mode="json"),
        }

    @application.get("/events/{event_id}")
    def event_detail(event_id: str) -> dict:
        return repository.get(event_id).model_dump(mode="json")

    @application.delete("/events/{event_id}")
    def delete_event(event_id: str) -> dict:
        repository.delete(event_id)
        for key in [key for key in selected_services if key[0] == event_id]:
            selected_services.pop(key, None)
        return {"deleted": event_id}

    @application.get("/storms")
    def storms(
        frame: int | None = None,
        event_id: str | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> list[dict]:
        return [
            item.model_dump(mode="json")
            for item in snapshot(frame, target_lat, target_lon, event_id).tracks
        ]

    @application.get("/storms/{storm_id}")
    def storm(
        storm_id: str,
        frame: int | None = None,
        event_id: str | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> dict:
        for item in snapshot(frame, target_lat, target_lon, event_id).tracks:
            if item.id == storm_id:
                return item.model_dump(mode="json")
        raise HTTPException(status_code=404, detail=f"Unknown active storm: {storm_id}")

    @application.get("/nowcast")
    def nowcast(
        frame: int | None = None,
        event_id: str | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> dict:
        return snapshot(frame, target_lat, target_lon, event_id).model_dump(mode="json")

    @application.get("/hazards")
    def hazards(
        frame: int | None = None,
        event_id: str | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> dict[str, list[dict]]:
        current = snapshot(frame, target_lat, target_lon, event_id)
        return {track.id: [item.model_dump(mode="json") for item in track.hazards] for track in current.tracks}

    @application.get("/alerts")
    def alerts(
        frame: int | None = None,
        event_id: str | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> list[dict]:
        current = snapshot(frame, target_lat, target_lon, event_id)
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
        event_id: str | None = None,
        target_lat: float = Query(default=configured.target.latitude, ge=-90, le=90),
        target_lon: float = Query(default=configured.target.longitude, ge=-180, le=180),
    ) -> list[dict]:
        current_service = service(event_id)
        selected = current_service.player.frame_count - 1 if frame is None else frame
        replay = current_service.player.analyze(selected, (target_lat, target_lon))
        metrics = evaluate_forecasts(replay.tracks, current_service.player.all_tracks())
        return [item.model_dump(mode="json") for item in metrics]

    return application


app = create_app()
