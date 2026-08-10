"""Validated access to normalized polygon-zone configuration."""

import hashlib
import hmac
import json
import math
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from packages.analytics.zone_engine import ZoneEngine


BEIJING_TIMEZONE = timezone(timedelta(hours=8))
ZONE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ZoneConfigUnavailable(RuntimeError):
    """Raised when the configured zones cannot be safely loaded."""


class ZoneSaveDisabled(RuntimeError):
    """Raised when the server has no sufficiently strong admin token."""


class ZoneAuthenticationFailed(RuntimeError):
    """Raised when a zone-save request has invalid credentials."""


class ZoneValidationFailed(ValueError):
    """Raised when a proposed zone configuration is unsafe."""


class ZoneVersionConflict(RuntimeError):
    """Raised when a caller attempts to replace a stale configuration."""


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _orientation(first, second, third):
    value = (
        (second[1] - first[1]) * (third[0] - second[0])
        - (second[0] - first[0]) * (third[1] - second[1])
    )
    if abs(value) <= 1e-12:
        return 0
    return 1 if value > 0 else 2


def _on_segment(first, point, second):
    return (
        min(first[0], second[0]) <= point[0] <= max(first[0], second[0])
        and min(first[1], second[1]) <= point[1] <= max(first[1], second[1])
    )


def _segments_intersect(first, second, third, fourth):
    first_orientation = _orientation(first, second, third)
    second_orientation = _orientation(first, second, fourth)
    third_orientation = _orientation(third, fourth, first)
    fourth_orientation = _orientation(third, fourth, second)
    if (
        first_orientation != second_orientation
        and third_orientation != fourth_orientation
    ):
        return True
    return (
        (first_orientation == 0 and _on_segment(first, third, second))
        or (second_orientation == 0 and _on_segment(first, fourth, second))
        or (third_orientation == 0 and _on_segment(third, first, fourth))
        or (fourth_orientation == 0 and _on_segment(third, second, fourth))
    )


def _validate_simple_polygon(points):
    if len(set(points)) != len(points):
        raise ZoneValidationFailed("polygon points must be unique")
    area = 0.0
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        area += point[0] * following[1] - following[0] * point[1]
    if abs(area) <= 1e-8:
        raise ZoneValidationFailed("polygon area must be greater than zero")

    edge_count = len(points)
    for first_index in range(edge_count):
        first_next = (first_index + 1) % edge_count
        for second_index in range(first_index + 1, edge_count):
            second_next = (second_index + 1) % edge_count
            if (
                first_index == second_index
                or first_next == second_index
                or second_next == first_index
            ):
                continue
            if _segments_intersect(
                points[first_index],
                points[first_next],
                points[second_index],
                points[second_next],
            ):
                raise ZoneValidationFailed(
                    "polygon edges must not intersect"
                )


class ZoneQueryService(object):
    API_SCHEMA_VERSION = "1.1"
    SAVE_CONFIRMATION = "SAVE_ZONE_CONFIG"
    TOKEN_MINIMUM_LENGTH = 16
    MAX_ZONES = 16
    MAX_POINTS = 32

    def __init__(
        self,
        config_path,
        admin_token=None,
        clock=None,
        default_config_path=None,
    ):
        self.config_path = os.path.abspath(config_path)
        self.default_config_path = (
            os.path.abspath(default_config_path)
            if default_config_path
            else None
        )
        self.admin_token = (
            admin_token
            if isinstance(admin_token, str)
            and len(admin_token) >= self.TOKEN_MINIMUM_LENGTH
            else None
        )
        self.clock = clock or (
            lambda: datetime.now(BEIJING_TIMEZONE)
        )
        self._lock = threading.RLock()

    @property
    def save_enabled(self):
        return self.admin_token is not None

    def get_zones(self):
        with self._lock:
            try:
                engine = ZoneEngine.from_file(self.config_path)
                version = self._current_version()
            except (OSError, KeyError, TypeError, ValueError) as error:
                raise ZoneConfigUnavailable(
                    "zone configuration is unavailable"
                ) from error
            zones = [self._serialize_zone(zone) for zone in engine.zones]
            return {
                "schema_version": self.API_SCHEMA_VERSION,
                "coordinate_space": "normalized",
                "config_version": version,
                "count": len(zones),
                "zones": zones,
                "read_only": not self.save_enabled,
                "save_enabled": self.save_enabled,
                "save_confirmation": self.SAVE_CONFIRMATION,
            }

    def get_default_zones(self):
        if not self.default_config_path:
            raise ZoneConfigUnavailable(
                "default zone configuration is unavailable"
            )
        try:
            engine = ZoneEngine.from_file(
                self.default_config_path
            )
            version = self._file_version(
                self.default_config_path
            )
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ZoneConfigUnavailable(
                "default zone configuration is unavailable"
            ) from error
        zones = [
            self._serialize_zone(zone) for zone in engine.zones
        ]
        return {
            "schema_version": self.API_SCHEMA_VERSION,
            "coordinate_space": "normalized",
            "default_version": version,
            "count": len(zones),
            "zones": zones,
            "read_only": True,
            "source": "factory_default",
        }

    def save_zones(self, payload, provided_token):
        self._authenticate(provided_token)
        normalized = self._normalize_request(payload)
        expected_version = normalized.pop("expected_version")
        normalized.pop("confirmation")

        with self._lock:
            current_version = self._current_version_or_unavailable()
            if not hmac.compare_digest(
                expected_version,
                current_version,
            ):
                raise ZoneVersionConflict(
                    "zone configuration changed; refresh before saving"
                )

            temporary_path = self._write_temporary(normalized)
            try:
                try:
                    ZoneEngine.from_file(temporary_path)
                except (OSError, KeyError, TypeError, ValueError) as error:
                    raise ZoneValidationFailed(
                        "proposed zone configuration is invalid"
                    ) from error

                current_version = self._current_version_or_unavailable()
                if not hmac.compare_digest(
                    expected_version,
                    current_version,
                ):
                    raise ZoneVersionConflict(
                        "zone configuration changed; refresh before saving"
                    )

                backup_path = self._backup_current()
                os.replace(temporary_path, self.config_path)
                temporary_path = None
            finally:
                if temporary_path and os.path.exists(temporary_path):
                    os.unlink(temporary_path)

            response = self.get_zones()
            response.update(
                {
                    "saved": True,
                    "saved_at": self.clock().isoformat(
                        timespec="milliseconds"
                    ),
                    "backup_path": self._public_backup_path(
                        backup_path
                    ),
                    "restart_required": False,
                    "hot_reload_expected": True,
                }
            )
            return response

    def _authenticate(self, provided_token):
        if not self.save_enabled:
            raise ZoneSaveDisabled(
                "zone saving is disabled on this server"
            )
        candidate = provided_token if isinstance(
            provided_token,
            str,
        ) else ""
        if not hmac.compare_digest(candidate, self.admin_token):
            raise ZoneAuthenticationFailed(
                "zone administrator token is invalid"
            )

    def _normalize_request(self, payload):
        if not isinstance(payload, dict):
            raise ZoneValidationFailed(
                "zone save payload must be an object"
            )
        allowed_keys = {
            "expected_version",
            "confirmation",
            "coordinate_space",
            "zones",
        }
        if set(payload) != allowed_keys:
            raise ZoneValidationFailed(
                "zone save payload fields are invalid"
            )
        expected_version = payload.get("expected_version")
        if (
            not isinstance(expected_version, str)
            or not re.match(r"^[0-9a-f]{64}$", expected_version)
        ):
            raise ZoneValidationFailed(
                "expected_version must be a SHA-256 value"
            )
        if payload.get("confirmation") != self.SAVE_CONFIRMATION:
            raise ZoneValidationFailed(
                "explicit save confirmation is required"
            )
        if payload.get("coordinate_space") != "normalized":
            raise ZoneValidationFailed(
                "coordinate_space must be normalized"
            )
        zones = payload.get("zones")
        if (
            not isinstance(zones, list)
            or not 1 <= len(zones) <= self.MAX_ZONES
        ):
            raise ZoneValidationFailed(
                "zones must contain between 1 and 16 items"
            )
        normalized_zones = [
            self._normalize_zone(zone) for zone in zones
        ]
        zone_ids = [zone["id"] for zone in normalized_zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ZoneValidationFailed("zone ids must be unique")
        return {
            "expected_version": expected_version,
            "confirmation": self.SAVE_CONFIRMATION,
            "coordinate_space": "normalized",
            "zones": normalized_zones,
        }

    def _normalize_zone(self, zone):
        if not isinstance(zone, dict):
            raise ZoneValidationFailed("each zone must be an object")
        allowed_keys = {
            "id",
            "name",
            "polygon",
            "target_classes",
            "anchor",
            "minimum_hits",
            "max_missed_frames",
        }
        if set(zone) != allowed_keys:
            raise ZoneValidationFailed("zone fields are invalid")

        zone_id = zone.get("id")
        if (
            not isinstance(zone_id, str)
            or not ZONE_ID_PATTERN.match(zone_id)
        ):
            raise ZoneValidationFailed(
                "zone id must use lowercase letters, digits, and underscores"
            )
        name = zone.get("name")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > 64
        ):
            raise ZoneValidationFailed(
                "zone name must contain 1 to 64 characters"
            )

        polygon = zone.get("polygon")
        if (
            not isinstance(polygon, list)
            or not 3 <= len(polygon) <= self.MAX_POINTS
        ):
            raise ZoneValidationFailed(
                "zone polygon must contain 3 to 32 points"
            )
        normalized_polygon = []
        for point in polygon:
            if (
                not isinstance(point, (list, tuple))
                or len(point) != 2
                or not _is_number(point[0])
                or not _is_number(point[1])
            ):
                raise ZoneValidationFailed(
                    "zone polygon points must contain two numbers"
                )
            x, y = float(point[0]), float(point[1])
            if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                raise ZoneValidationFailed(
                    "normalized zone coordinates must be 0..1"
                )
            normalized_polygon.append(
                (round(x, 6), round(y, 6))
            )
        _validate_simple_polygon(normalized_polygon)

        target_classes = zone.get("target_classes")
        if (
            not isinstance(target_classes, list)
            or len(target_classes) > 32
        ):
            raise ZoneValidationFailed(
                "target_classes must be a list of at most 32 items"
            )
        normalized_classes = []
        for class_name in target_classes:
            if (
                not isinstance(class_name, str)
                or not class_name.strip()
                or len(class_name.strip()) > 64
            ):
                raise ZoneValidationFailed(
                    "target class names must contain 1 to 64 characters"
                )
            normalized_classes.append(class_name.strip())
        if len(normalized_classes) != len(set(normalized_classes)):
            raise ZoneValidationFailed(
                "target class names must be unique"
            )

        anchor = zone.get("anchor")
        if anchor not in ("center", "bottom_center"):
            raise ZoneValidationFailed("zone anchor is invalid")
        minimum_hits = self._bounded_integer(
            zone.get("minimum_hits"),
            "minimum_hits",
            1,
            1000,
        )
        max_missed_frames = self._bounded_integer(
            zone.get("max_missed_frames"),
            "max_missed_frames",
            0,
            1000,
        )
        return {
            "id": zone_id,
            "name": name.strip(),
            "polygon": [
                [point[0], point[1]]
                for point in normalized_polygon
            ],
            "target_classes": normalized_classes,
            "anchor": anchor,
            "minimum_hits": minimum_hits,
            "max_missed_frames": max_missed_frames,
        }

    @staticmethod
    def _bounded_integer(value, name, minimum, maximum):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not minimum <= value <= maximum
        ):
            raise ZoneValidationFailed(
                "{0} must be between {1} and {2}".format(
                    name,
                    minimum,
                    maximum,
                )
            )
        return value

    @staticmethod
    def _serialize_zone(zone):
        return {
            "id": zone.zone_id,
            "name": zone.name,
            "polygon": [
                [round(point[0], 6), round(point[1], 6)]
                for point in zone.polygon
            ],
            "target_classes": sorted(zone.target_classes),
            "anchor": zone.anchor,
            "minimum_hits": zone.minimum_hits,
            "max_missed_frames": zone.max_missed_frames,
        }

    def _current_version(self):
        return self._file_version(self.config_path)

    @staticmethod
    def _file_version(path):
        digest = hashlib.sha256()
        with open(path, "rb") as config_file:
            while True:
                block = config_file.read(65536)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()

    def _current_version_or_unavailable(self):
        try:
            return self._current_version()
        except OSError as error:
            raise ZoneConfigUnavailable(
                "zone configuration is unavailable"
            ) from error

    def _write_temporary(self, payload):
        config_directory = os.path.dirname(self.config_path)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".zones-",
            suffix=".tmp",
            dir=config_directory,
        )
        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as output:
                json.dump(
                    payload,
                    output,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=False,
                )
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            try:
                source_stat = os.stat(self.config_path)
                os.chmod(
                    temporary_path,
                    source_stat.st_mode & 0o777,
                )
                self._preserve_ownership(
                    temporary_path,
                    source_stat,
                )
            except OSError:
                pass
            return temporary_path
        except Exception:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
            raise

    def _backup_current(self):
        backup_directory = os.path.join(
            os.path.dirname(self.config_path),
            "backups",
        )
        os.makedirs(backup_directory, exist_ok=True)
        source_stat = os.stat(self.config_path)
        self._preserve_ownership(
            backup_directory,
            source_stat,
        )
        timestamp = self.clock().strftime("%Y%m%dT%H%M%S%f%z")
        backup_path = os.path.join(
            backup_directory,
            "zones-{0}.json".format(timestamp),
        )
        shutil.copy2(self.config_path, backup_path)
        self._preserve_ownership(backup_path, source_stat)
        with open(backup_path, "rb") as backup_file:
            try:
                os.fsync(backup_file.fileno())
            except OSError:
                pass
        return backup_path

    def _public_backup_path(self, backup_path):
        config_directory = os.path.dirname(self.config_path)
        return os.path.join(
            os.path.basename(config_directory),
            "backups",
            os.path.basename(backup_path),
        ).replace(os.sep, "/")

    @staticmethod
    def _preserve_ownership(path, source_stat):
        if not hasattr(os, "chown"):
            return
        try:
            os.chown(path, source_stat.st_uid, source_stat.st_gid)
        except (AttributeError, OSError):
            pass
