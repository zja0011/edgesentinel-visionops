"""Bounded read-only current weather lookup using fixed HTTPS APIs."""

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from packages.vision.schemas import beijing_timestamp


GEOCODING_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
MAX_RESPONSE_BYTES = 256 * 1024

WEATHER_CODE_LABELS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snowfall",
    73: "moderate snowfall",
    75: "heavy snowfall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class WeatherUnavailable(RuntimeError):
    pass


class CurrentWeatherTools(object):
    def __init__(
        self,
        default_location=None,
        opener=None,
        timeout_seconds=8.0,
    ):
        self.default_location = self._normalize_optional_location(
            default_location
        )
        self.opener = opener or urlopen
        self.timeout_seconds = max(
            1.0,
            min(float(timeout_seconds), 15.0),
        )

    def get_current(self, arguments):
        requested = self._normalize_optional_location(
            (arguments or {}).get("location")
        )
        location_query = requested or self.default_location
        if not location_query:
            raise WeatherUnavailable(
                "location is required because no default weather "
                "location is configured"
            )

        place = self._geocode(location_query)
        current_payload = self._forecast(
            place["latitude"],
            place["longitude"],
        )
        current = current_payload.get("current") or {}
        units = current_payload.get("current_units") or {}
        weather_code = self._integer_or_none(
            current.get("weather_code")
        )
        return {
            "schema_version": "1.0",
            "provider": "open-meteo",
            "queried_at": beijing_timestamp(),
            "location": {
                "query": location_query,
                "name": place.get("name"),
                "admin1": place.get("admin1"),
                "country": place.get("country"),
                "country_code": place.get("country_code"),
                "latitude": place.get("latitude"),
                "longitude": place.get("longitude"),
                "timezone": current_payload.get("timezone"),
            },
            "current": {
                "timestamp": current.get("time"),
                "temperature_c": current.get("temperature_2m"),
                "apparent_temperature_c": current.get(
                    "apparent_temperature"
                ),
                "relative_humidity_percent": current.get(
                    "relative_humidity_2m"
                ),
                "precipitation_mm": current.get("precipitation"),
                "weather_code": weather_code,
                "condition": WEATHER_CODE_LABELS.get(
                    weather_code,
                    "unknown",
                ),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "wind_direction_degrees": current.get(
                    "wind_direction_10m"
                ),
                "is_day": current.get("is_day"),
            },
            "units": {
                "temperature": units.get(
                    "temperature_2m",
                    "\u00b0C",
                ),
                "apparent_temperature": units.get(
                    "apparent_temperature",
                    "\u00b0C",
                ),
                "relative_humidity": units.get(
                    "relative_humidity_2m",
                    "%",
                ),
                "precipitation": units.get("precipitation", "mm"),
                "wind_speed": units.get("wind_speed_10m", "km/h"),
                "wind_direction": units.get(
                    "wind_direction_10m",
                    "\u00b0",
                ),
            },
            "external_request": True,
            "read_only": True,
        }

    def _geocode(self, location):
        payload = self._get_json(
            GEOCODING_ENDPOINT
            + "?"
            + urlencode(
                {
                    "name": location,
                    "count": 1,
                    "language": "zh",
                    "format": "json",
                }
            )
        )
        results = payload.get("results") or []
        if not results:
            raise WeatherUnavailable(
                "weather location was not found"
            )
        result = results[0]
        try:
            latitude = float(result["latitude"])
            longitude = float(result["longitude"])
        except (KeyError, TypeError, ValueError):
            raise WeatherUnavailable(
                "weather geocoding result is invalid"
            )
        return {
            "name": str(result.get("name") or location)[:100],
            "admin1": self._bounded_optional(result.get("admin1")),
            "country": self._bounded_optional(result.get("country")),
            "country_code": self._bounded_optional(
                result.get("country_code"),
                8,
            ),
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
        }

    def _forecast(self, latitude, longitude):
        payload = self._get_json(
            FORECAST_ENDPOINT
            + "?"
            + urlencode(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": (
                        "temperature_2m,relative_humidity_2m,"
                        "apparent_temperature,precipitation,"
                        "weather_code,wind_speed_10m,"
                        "wind_direction_10m,is_day"
                    ),
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                    "precipitation_unit": "mm",
                    "timezone": "auto",
                    "forecast_days": 1,
                }
            )
        )
        if not isinstance(payload.get("current"), dict):
            raise WeatherUnavailable(
                "current weather response is unavailable"
            )
        return payload

    def _get_json(self, url):
        try:
            response = self.opener(
                url,
                timeout=self.timeout_seconds,
            )
            try:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except Exception as error:
            raise WeatherUnavailable(
                "weather provider request failed"
            ) from error
        if len(raw) > MAX_RESPONSE_BYTES:
            raise WeatherUnavailable(
                "weather provider response is too large"
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise WeatherUnavailable(
                "weather provider returned invalid JSON"
            ) from error
        if not isinstance(payload, dict) or payload.get("error"):
            raise WeatherUnavailable(
                "weather provider returned an error"
            )
        return payload

    @staticmethod
    def _normalize_optional_location(value):
        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        if not normalized:
            return None
        if len(normalized) > 80:
            raise WeatherUnavailable(
                "weather location must not exceed 80 characters"
            )
        if any(ord(character) < 32 for character in normalized):
            raise WeatherUnavailable(
                "weather location contains control characters"
            )
        return normalized

    @staticmethod
    def _bounded_optional(value, maximum=100):
        if value is None:
            return None
        return str(value)[:maximum]

    @staticmethod
    def _integer_or_none(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
