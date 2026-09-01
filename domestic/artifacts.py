"""Versioned JSON artifacts for dashboards and serverless endpoints."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ARTIFACT_SCHEMA = "football.predictions.artifact"
ARTIFACT_SCHEMA_VERSION = "1.0.0"

ARTIFACT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": f"https://fb-preds.vercel.app/schemas/artifact-{ARTIFACT_SCHEMA_VERSION}.json",
    "title": "Football prediction artifact",
    "type": "object",
    "required": [
        "schema",
        "schema_version",
        "product",
        "artifact_type",
        "generated_at",
        "metadata",
        "data",
    ],
    "properties": {
        "schema": {"const": ARTIFACT_SCHEMA},
        "schema_version": {"const": ARTIFACT_SCHEMA_VERSION},
        "product": {"type": "string", "minLength": 1},
        "artifact_type": {"type": "string", "minLength": 1},
        "generated_at": {"type": "string", "format": "date-time"},
        "metadata": {"type": "object"},
        "data": {},
    },
    "additionalProperties": False,
}


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _timestamp(value: datetime | str | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def artifact_envelope(
    *,
    product: str,
    artifact_type: str,
    data: Any,
    metadata: Mapping[str, Any] | None = None,
    generated_at: datetime | str | None = None,
) -> dict[str, Any]:
    if not product.strip() or not artifact_type.strip():
        raise ValueError("product and artifact_type are required")
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "product": product,
        "artifact_type": artifact_type,
        "generated_at": _timestamp(generated_at),
        "metadata": _jsonable(metadata or {}),
        "data": _jsonable(data),
    }
    validate_artifact(artifact)
    return artifact


def season_forecast_artifact(
    forecast: Any,
    *,
    metadata: Mapping[str, Any] | None = None,
    generated_at: datetime | str | None = None,
) -> dict[str, Any]:
    details = dict(metadata or {})
    for field in ("league", "season", "model", "simulations", "seed"):
        value = getattr(forecast, field, None)
        if value is not None:
            details.setdefault(field, value)
    return artifact_envelope(
        product="domestic_league",
        artifact_type="season_forecast",
        data=forecast,
        metadata=details,
        generated_at=generated_at,
    )


def match_breakdown_artifact(
    breakdown: Any,
    *,
    league: str | None = None,
    season: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    generated_at: datetime | str | None = None,
) -> dict[str, Any]:
    details = dict(metadata or {})
    for key, value in (("league", league), ("season", season)):
        if value is not None:
            details.setdefault(key, value)
    for field in ("home_team", "away_team", "model"):
        value = getattr(breakdown, field, None)
        if value is not None:
            details.setdefault(field, value)
    return artifact_envelope(
        product="domestic_league",
        artifact_type="match_breakdown",
        data=breakdown,
        metadata=details,
        generated_at=generated_at,
    )


def match_breakdowns_artifact(
    breakdowns: Sequence[Any],
    *,
    league: str | None = None,
    season: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    generated_at: datetime | str | None = None,
) -> dict[str, Any]:
    details = dict(metadata or {})
    if league is not None:
        details.setdefault("league", league)
    if season is not None:
        details.setdefault("season", season)
    details.setdefault("match_count", len(breakdowns))
    return artifact_envelope(
        product="domestic_league",
        artifact_type="match_breakdowns",
        data=list(breakdowns),
        metadata=details,
        generated_at=generated_at,
    )


def validate_artifact(artifact: Mapping[str, Any]) -> None:
    required = ARTIFACT_JSON_SCHEMA["required"]
    missing = [field for field in required if field not in artifact]
    if missing:
        raise ValueError(f"Artifact is missing fields: {missing}")
    if artifact["schema"] != ARTIFACT_SCHEMA:
        raise ValueError(f"Unsupported artifact schema: {artifact['schema']!r}")
    if artifact["schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported artifact schema version: {artifact['schema_version']!r}"
        )
    if not isinstance(artifact["metadata"], Mapping):
        raise ValueError("Artifact metadata must be an object")


def json_dumps(value: Any, *, pretty: bool = False) -> str:
    options: dict[str, Any] = {
        "allow_nan": False,
        "ensure_ascii": False,
        "sort_keys": True,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return json.dumps(_jsonable(value), **options)


def artifact_etag(artifact: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json_dumps(artifact).encode("utf-8")).hexdigest()
    return f'"{digest}"'


def write_json_artifact(
    path: str | Path,
    artifact: Mapping[str, Any],
    *,
    pretty: bool = False,
) -> Path:
    validate_artifact(artifact)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(json_dumps(artifact, pretty=pretty) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def read_json_artifact(path: str | Path) -> dict[str, Any]:
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_artifact(artifact)
    return artifact


def vercel_response(
    artifact: Mapping[str, Any],
    *,
    status: int = 200,
    cache_control: str = "public, max-age=0, s-maxage=300, stale-while-revalidate=86400",
) -> dict[str, Any]:
    body = json_dumps(artifact)
    return {
        "statusCode": int(status),
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": cache_control,
            "ETag": artifact_etag(artifact),
            "Content-Length": str(len(body.encode("utf-8"))),
        },
        "body": body,
    }


__all__ = [
    "ARTIFACT_JSON_SCHEMA",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "artifact_envelope",
    "artifact_etag",
    "json_dumps",
    "match_breakdown_artifact",
    "match_breakdowns_artifact",
    "read_json_artifact",
    "season_forecast_artifact",
    "validate_artifact",
    "vercel_response",
    "write_json_artifact",
]
