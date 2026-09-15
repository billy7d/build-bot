"""Đóng băng và kiểm tra integrity của intelligence bundle Phase 2."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..features.fingerprint import fingerprint
from ..features.registry import FEATURE_SET_VERSION, metadata_dict
from .models import PHASE3_BUNDLE_VERSION, format_utc_timestamp, parse_utc_timestamp, utc_now


class BundleError(ValueError):
    """Bundle không hợp lệ hoặc đã bị thay đổi."""


class BundleMismatchError(BundleError):
    """Bundle không khớp fingerprint/code contract kỳ vọng."""


class BundleMutationError(BundleError):
    """Phát hiện thay đổi trên bundle đã đóng băng."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _component_fingerprint(value: Any, fallback: str = "") -> str:
    if isinstance(value, str) and value:
        return value
    return fingerprint(value if value is not None else {"missing": True, "fallback": fallback})


def _enabled(value: Any) -> bool:
    """Nhận diện cờ execution ở cả dạng bool và chuỗi khi validate manifest."""

    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ShadowBundle:
    """Manifest bất biến của toàn bộ intelligence dùng cho một forward run."""

    bundle_id: str
    bundle_version: str
    created_at_utc: str
    phase1_fingerprint: str
    phase2_base_sha: str
    feature_set_version: str
    feature_fingerprint: str
    preprocessing_fingerprint: str
    regime_version: str
    regime_fingerprint: str
    similarity_version: str
    similarity_fingerprint: str
    model_version: str
    model_fingerprint: str
    calibration_fingerprint: str
    historical_reference_cutoff_utc: str
    seed: int
    config_json: Mapping[str, Any]
    status: str = "FROZEN"

    def fingerprint_material(self) -> dict[str, Any]:
        """Material không chứa thời gian tạo để ID có tính deterministic."""

        config = dict(self.config_json)
        # Model payload có thể nằm ở artifact cục bộ; manifest review chỉ giữ fingerprint.
        config.pop("model_bundle", None)
        return {
            "bundle_version": self.bundle_version,
            "phase1_fingerprint": self.phase1_fingerprint,
            "phase2_base_sha": self.phase2_base_sha,
            "feature_set_version": self.feature_set_version,
            "feature_fingerprint": self.feature_fingerprint,
            "preprocessing_fingerprint": self.preprocessing_fingerprint,
            "regime_version": self.regime_version,
            "regime_fingerprint": self.regime_fingerprint,
            "similarity_version": self.similarity_version,
            "similarity_fingerprint": self.similarity_fingerprint,
            "model_version": self.model_version,
            "model_fingerprint": self.model_fingerprint,
            "calibration_fingerprint": self.calibration_fingerprint,
            "historical_reference_cutoff_utc": self.historical_reference_cutoff_utc,
            "seed": self.seed,
            "config": config,
        }

    def recompute_id(self) -> str:
        return "p3-bundle-" + fingerprint(self.fingerprint_material())

    def to_dict(self, *, include_model_payload: bool = True) -> dict[str, Any]:
        value = {
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "created_at_utc": self.created_at_utc,
            "phase1_fingerprint": self.phase1_fingerprint,
            "phase2_base_sha": self.phase2_base_sha,
            "feature_set_version": self.feature_set_version,
            "feature_fingerprint": self.feature_fingerprint,
            "preprocessing_fingerprint": self.preprocessing_fingerprint,
            "regime_version": self.regime_version,
            "regime_fingerprint": self.regime_fingerprint,
            "similarity_version": self.similarity_version,
            "similarity_fingerprint": self.similarity_fingerprint,
            "model_version": self.model_version,
            "model_fingerprint": self.model_fingerprint,
            "calibration_fingerprint": self.calibration_fingerprint,
            "historical_reference_cutoff_utc": self.historical_reference_cutoff_utc,
            "seed": self.seed,
            "status": self.status,
            "config": dict(self.config_json),
        }
        if not include_model_payload:
            config = dict(value["config"])
            config.pop("model_bundle", None)
            value["config"] = config
        return value

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ShadowBundle":
        config = payload.get("config", payload.get("config_json", {}))
        if not isinstance(config, Mapping):
            raise BundleError("bundle config must be a mapping")
        return cls(
            bundle_id=str(payload.get("bundle_id", "")),
            bundle_version=str(payload.get("bundle_version", PHASE3_BUNDLE_VERSION)),
            created_at_utc=str(payload.get("created_at_utc", "1970-01-01T00:00:00Z")),
            phase1_fingerprint=str(payload.get("phase1_fingerprint", "")),
            phase2_base_sha=str(payload.get("phase2_base_sha", "")),
            feature_set_version=str(payload.get("feature_set_version", FEATURE_SET_VERSION)),
            feature_fingerprint=str(payload.get("feature_fingerprint", "")),
            preprocessing_fingerprint=str(payload.get("preprocessing_fingerprint", "")),
            regime_version=str(payload.get("regime_version", "regime/1")),
            regime_fingerprint=str(payload.get("regime_fingerprint", "")),
            similarity_version=str(payload.get("similarity_version", "similarity/1")),
            similarity_fingerprint=str(payload.get("similarity_fingerprint", "")),
            model_version=str(payload.get("model_version", "scoring/1")),
            model_fingerprint=str(payload.get("model_fingerprint", "")),
            calibration_fingerprint=str(payload.get("calibration_fingerprint", "")),
            historical_reference_cutoff_utc=str(payload.get("historical_reference_cutoff_utc", "")),
            seed=int(payload.get("seed", 42)),
            config_json=dict(config),
            status=str(payload.get("status", "FROZEN")),
        )


def freeze_bundle(
    *,
    phase1_fingerprint: str,
    phase2_base_sha: str,
    feature_manifest: Mapping[str, Any],
    regime_manifest: Mapping[str, Any],
    model_manifest: Mapping[str, Any] | None = None,
    model_bundle: Mapping[str, Any] | None = None,
    similarity_config: Mapping[str, Any] | None = None,
    historical_reference_cutoff_utc: str | None = None,
    seed: int = 42,
    created_at_utc: str | None = None,
    ood_config: Mapping[str, Any] | None = None,
    confidence_config: Mapping[str, Any] | None = None,
) -> ShadowBundle:
    """Tạo bundle từ manifest Phase 2 mà không fit lại hay nhìn outcome forward."""

    if not phase1_fingerprint or not phase2_base_sha:
        raise BundleError("phase1 fingerprint and phase2 base SHA are required")
    cutoff = historical_reference_cutoff_utc
    if not cutoff:
        cutoff = str(feature_manifest.get("training_cutoff") or feature_manifest.get("train_end") or "")
    if not cutoff and isinstance(model_bundle, Mapping):
        cutoff = str(model_bundle.get("training_cutoff") or "")
    if not cutoff:
        raise BundleError("historical_reference_cutoff_utc is required to freeze a bundle")
    cutoff = format_utc_timestamp(cutoff)

    feature_manifest = dict(feature_manifest)
    regime_manifest = dict(regime_manifest)
    model_manifest = dict(model_manifest or {})
    model_payload = dict(model_bundle or {}) if isinstance(model_bundle, Mapping) else None
    similarity_payload = dict(similarity_config or {"version": regime_manifest.get("similarity_version", "similarity/1")})
    regime_config_payload = {
        "version": regime_manifest.get("regime_version", "regime/1"),
        "threshold_source": regime_manifest.get("threshold_source", "TRAIN_DISTRIBUTION_AND_STRATEGY_SEMANTICS"),
        "training_cutoff": regime_manifest.get("training_cutoff"),
        "training_ids": regime_manifest.get("training_ids", []),
        "thresholds": regime_manifest.get("threshold_values", regime_manifest.get("thresholds", {})),
    }
    if isinstance(regime_manifest.get("config"), Mapping):
        regime_config_payload.update(dict(regime_manifest["config"]))

    feature_fingerprint = _component_fingerprint(feature_manifest.get("feature_fingerprint"), "feature-manifest")
    preprocessing_fingerprint = _component_fingerprint(
        feature_manifest.get("preprocessing_fingerprint")
        or (model_payload or {}).get("preprocessor", {}).get("preprocessing_fingerprint"),
        "preprocessing",
    )
    regime_fingerprint = _component_fingerprint(
        regime_manifest.get("regime_fingerprint")
        or _mapping(regime_manifest.get("validation")).get("regime_fingerprint"),
        "regime",
    )
    similarity_fingerprint = _component_fingerprint(
        similarity_payload.get("similarity_fingerprint") or similarity_payload.get("fingerprint"),
        "similarity",
    )
    model_version = str(model_manifest.get("model_version") or (model_payload or {}).get("model_version") or "scoring/1")
    model_fingerprint = _component_fingerprint(
        model_manifest.get("model_fingerprint") or model_manifest.get("fingerprint") or model_payload,
        "model",
    )
    calibration_payload = (model_payload or {}).get("calibrator", model_manifest.get("calibration", {}))
    calibration_fingerprint = _component_fingerprint(
        model_manifest.get("calibration_fingerprint") or calibration_payload,
        "calibration",
    )
    feature_order = feature_manifest.get("output_names") or feature_manifest.get("allowlist") or []
    preprocessor_payload = (model_payload or {}).get("preprocessor") or feature_manifest.get("preprocessor", {})
    config: dict[str, Any] = {
        "feature_manifest": {
            "schema": feature_manifest.get("schema"),
            "feature_set_version": feature_manifest.get("feature_set_version", feature_manifest.get("feature_version", FEATURE_SET_VERSION)),
            "allowlist": feature_manifest.get("allowlist", []),
            "definitions": feature_manifest.get("definitions", metadata_dict()),
            "bar_state": feature_manifest.get("bar_state", "closed_bar"),
            "available_at": feature_manifest.get("available_at", "opportunity_timestamp_utc"),
            "lookback": feature_manifest.get("lookback", "per_definition"),
            "source_timestamp": feature_manifest.get("source_timestamp", "event_timestamp_utc"),
        },
        "feature_order": list(feature_order),
        "preprocessor": preprocessor_payload if isinstance(preprocessor_payload, Mapping) else {},
        "regime_config": regime_config_payload,
        "similarity_config": similarity_payload,
        "model_manifest": model_manifest,
        "model_bundle": model_payload,
        "model_payload_fingerprint": fingerprint(model_payload) if model_payload is not None else None,
        "calibration_config": calibration_payload if isinstance(calibration_payload, Mapping) else {},
        "ood_config": dict(ood_config or {"source": "phase2_train_only_preprocessor", "severe_policy": "NO_OPINION"}),
        "confidence_config": dict(confidence_config or {"source": "feature_ood_support_regime_calibration"}),
        "historical_reference_cutoff_utc": cutoff,
        "seed": int(seed),
        "execution_mode": "NONE",
        "live_execution_enabled": False,
        "execution_authority": "NONE",
        "trade_control_authority": "NONE",
        "position_control_authority": "NONE",
        "risk_control_authority": "NONE",
    }
    feature_set_version = str(feature_manifest.get("feature_set_version") or feature_manifest.get("feature_version") or FEATURE_SET_VERSION)
    regime_version = str(regime_manifest.get("regime_version") or regime_config_payload.get("version") or "regime/1")
    similarity_version = str(similarity_payload.get("version") or regime_manifest.get("similarity_version") or "similarity/1")
    bundle = ShadowBundle(
        bundle_id="",
        bundle_version=PHASE3_BUNDLE_VERSION,
        created_at_utc=format_utc_timestamp(created_at_utc or utc_now()),
        phase1_fingerprint=phase1_fingerprint,
        phase2_base_sha=phase2_base_sha,
        feature_set_version=feature_set_version,
        feature_fingerprint=feature_fingerprint,
        preprocessing_fingerprint=preprocessing_fingerprint,
        regime_version=regime_version,
        regime_fingerprint=regime_fingerprint,
        similarity_version=similarity_version,
        similarity_fingerprint=similarity_fingerprint,
        model_version=model_version,
        model_fingerprint=model_fingerprint,
        calibration_fingerprint=calibration_fingerprint,
        historical_reference_cutoff_utc=cutoff,
        seed=int(seed),
        config_json=config,
        status="FROZEN",
    )
    # ID dùng cùng material với manifest đã loại payload model để không đổi giữa local/CI.
    return ShadowBundle(bundle_id=bundle.recompute_id(), **{
        field: getattr(bundle, field)
        for field in bundle.__dataclass_fields__
        if field != "bundle_id"
    })


def validate_bundle(
    bundle: ShadowBundle | Mapping[str, Any],
    *,
    expected_phase1_fingerprint: str | None = None,
    expected_phase2_base_sha: str | None = None,
) -> ShadowBundle:
    """Fail closed nếu bundle thiếu field, sai ID hoặc sai provenance."""

    value = bundle if isinstance(bundle, ShadowBundle) else ShadowBundle.from_dict(bundle)
    required = (
        value.bundle_id, value.phase1_fingerprint, value.phase2_base_sha,
        value.feature_fingerprint, value.preprocessing_fingerprint,
        value.regime_fingerprint, value.similarity_fingerprint,
        value.model_fingerprint, value.calibration_fingerprint,
        value.historical_reference_cutoff_utc,
    )
    if value.status != "FROZEN" or any(not item for item in required):
        raise BundleError("bundle is not complete and FROZEN")
    try:
        parse_utc_timestamp(value.created_at_utc)
        parse_utc_timestamp(value.historical_reference_cutoff_utc)
    except ValueError as exc:
        raise BundleError(str(exc)) from exc
    if expected_phase1_fingerprint and value.phase1_fingerprint != expected_phase1_fingerprint:
        raise BundleMismatchError("Phase 1 fingerprint does not match the frozen bundle")
    if expected_phase2_base_sha and value.phase2_base_sha != expected_phase2_base_sha:
        raise BundleMismatchError("Phase 2 base SHA does not match the frozen bundle")
    if value.recompute_id() != value.bundle_id:
        raise BundleMutationError("bundle_id does not match immutable bundle material")
    model_payload = value.config_json.get("model_bundle")
    payload_fingerprint = value.config_json.get("model_payload_fingerprint")
    if model_payload is not None and not isinstance(model_payload, Mapping):
        raise BundleError("embedded model payload must be a mapping")
    if isinstance(model_payload, Mapping):
        if not payload_fingerprint:
            raise BundleMutationError("embedded model payload has no frozen fingerprint")
        if fingerprint(model_payload) != str(payload_fingerprint):
            raise BundleMutationError("embedded model payload does not match frozen fingerprint")
    authority_keys = (
        "execution_authority", "trade_control_authority",
        "position_control_authority", "risk_control_authority",
    )
    if value.config_json.get("execution_mode") != "NONE" or value.config_json.get("live_execution_enabled") is not False or _enabled(value.config_json.get("execution_enabled")) or any(value.config_json.get(key) != "NONE" for key in authority_keys):
        raise BundleError("Phase 3 bundle has execution authority")
    return value


def assert_bundle_immutable(before: ShadowBundle, after: ShadowBundle) -> None:
    """So sánh material, không cho sửa bundle đã được dùng trong run."""

    for value in (before, after):
        model_payload = value.config_json.get("model_bundle")
        payload_fingerprint = value.config_json.get("model_payload_fingerprint")
        if model_payload is not None and not isinstance(model_payload, Mapping):
            raise BundleMutationError("embedded model payload must be a mapping")
        if isinstance(model_payload, Mapping):
            if not payload_fingerprint or fingerprint(model_payload) != str(payload_fingerprint):
                raise BundleMutationError("embedded model payload does not match frozen fingerprint")
    if before.bundle_id != after.bundle_id or before.fingerprint_material() != after.fingerprint_material():
        raise BundleMutationError("frozen bundle mutation detected")


def persist_bundle(connection: sqlite3.Connection, bundle: ShadowBundle) -> None:
    """Insert một lần; bản ghi cùng ID phải có config giống hệt."""

    bundle = validate_bundle(bundle)
    payload = json.dumps(dict(bundle.config_json), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    existing = connection.execute(
        "SELECT config_json, bundle_id FROM phase3_shadow_bundles WHERE bundle_id = ?",
        (bundle.bundle_id,),
    ).fetchone()
    if existing:
        if str(existing[0]) != payload:
            raise BundleMutationError("existing persisted bundle has different config")
        return
    connection.execute(
        """
        INSERT INTO phase3_shadow_bundles(
            bundle_id, bundle_version, created_at_utc, phase1_fingerprint,
            phase2_base_sha, feature_set_version, feature_fingerprint,
            preprocessing_fingerprint, regime_version, regime_fingerprint,
            similarity_version, similarity_fingerprint, model_version,
            model_fingerprint, calibration_fingerprint,
            historical_reference_cutoff_utc, seed, config_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bundle.bundle_id, bundle.bundle_version, bundle.created_at_utc,
            bundle.phase1_fingerprint, bundle.phase2_base_sha,
            bundle.feature_set_version, bundle.feature_fingerprint,
            bundle.preprocessing_fingerprint, bundle.regime_version,
            bundle.regime_fingerprint, bundle.similarity_version,
            bundle.similarity_fingerprint, bundle.model_version,
            bundle.model_fingerprint, bundle.calibration_fingerprint,
            bundle.historical_reference_cutoff_utc, bundle.seed, payload,
            bundle.status,
        ),
    )


def load_persisted_bundle(connection: sqlite3.Connection, bundle_id: str) -> ShadowBundle:
    row = connection.execute(
        "SELECT * FROM phase3_shadow_bundles WHERE bundle_id = ?", (bundle_id,)
    ).fetchone()
    if row is None:
        raise BundleMismatchError(f"unknown frozen bundle: {bundle_id}")
    value = dict(row)
    value["config"] = json.loads(value.pop("config_json"))
    return validate_bundle(value)


def write_bundle_manifest(bundle: ShadowBundle, output: str | Path) -> None:
    """Ghi manifest reviewable, không nhúng model payload lớn vào report."""

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle.to_dict(include_model_payload=False), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "BundleError",
    "BundleMismatchError",
    "BundleMutationError",
    "ShadowBundle",
    "assert_bundle_immutable",
    "freeze_bundle",
    "load_persisted_bundle",
    "persist_bundle",
    "validate_bundle",
    "write_bundle_manifest",
]
