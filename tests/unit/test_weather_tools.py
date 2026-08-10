import json
import unittest
from urllib.parse import parse_qs, urlparse

from packages.harness.weather_tools import (
    CurrentWeatherTools,
    WeatherUnavailable,
)


class FakeResponse(object):
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
        self.closed = False

    def read(self, unused_size):
        return self.payload

    def close(self):
        self.closed = True


class WeatherToolsTests(unittest.TestCase):
    def setUp(self):
        self.urls = []

        def opener(url, timeout):
            self.urls.append((url, timeout))
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            if "geocoding-api.open-meteo.com" in parsed.netloc:
                self.assertEqual(query["name"], ["深圳"])
                return FakeResponse(
                    {
                        "results": [
                            {
                                "name": "深圳",
                                "admin1": "广东",
                                "country": "中国",
                                "country_code": "CN",
                                "latitude": 22.54554,
                                "longitude": 114.0683,
                            }
                        ]
                    }
                )
            self.assertEqual(query["timezone"], ["auto"])
            self.assertEqual(query["forecast_days"], ["1"])
            return FakeResponse(
                {
                    "timezone": "Asia/Shanghai",
                    "current_units": {
                        "temperature_2m": "°C",
                        "relative_humidity_2m": "%",
                        "apparent_temperature": "°C",
                        "precipitation": "mm",
                        "wind_speed_10m": "km/h",
                        "wind_direction_10m": "°",
                    },
                    "current": {
                        "time": "2026-07-29T20:30",
                        "temperature_2m": 30.1,
                        "relative_humidity_2m": 76,
                        "apparent_temperature": 35.0,
                        "precipitation": 0.0,
                        "weather_code": 2,
                        "wind_speed_10m": 8.4,
                        "wind_direction_10m": 135,
                        "is_day": 0,
                    },
                }
            )

        self.opener = opener

    def test_returns_bounded_current_weather(self):
        tool = CurrentWeatherTools(opener=self.opener)

        result = tool.get_current({"location": " 深圳 "})

        self.assertEqual(result["provider"], "open-meteo")
        self.assertEqual(result["location"]["name"], "深圳")
        self.assertEqual(
            result["location"]["timezone"],
            "Asia/Shanghai",
        )
        self.assertEqual(result["current"]["temperature_c"], 30.1)
        self.assertEqual(result["current"]["condition"], "partly cloudy")
        self.assertTrue(result["external_request"])
        self.assertTrue(result["read_only"])
        self.assertEqual(len(self.urls), 2)
        self.assertTrue(
            all(url.startswith("https://") for url, unused in self.urls)
        )

    def test_uses_configured_default_location(self):
        tool = CurrentWeatherTools(
            default_location="深圳",
            opener=self.opener,
        )

        result = tool.get_current({})

        self.assertEqual(result["location"]["query"], "深圳")

    def test_missing_location_fails_without_network(self):
        tool = CurrentWeatherTools(opener=self.opener)

        with self.assertRaises(WeatherUnavailable):
            tool.get_current({})

        self.assertEqual(self.urls, [])

    def test_invalid_or_unknown_location_is_bounded(self):
        tool = CurrentWeatherTools(opener=self.opener)
        with self.assertRaises(WeatherUnavailable):
            tool.get_current({"location": "x" * 81})

        empty = CurrentWeatherTools(
            opener=lambda unused_url, timeout: FakeResponse(
                {"results": []}
            )
        )
        with self.assertRaises(WeatherUnavailable):
            empty.get_current({"location": "unknown"})


if __name__ == "__main__":
    unittest.main()
