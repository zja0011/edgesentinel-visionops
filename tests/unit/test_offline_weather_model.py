import unittest

from packages.harness.mock_model import OfflineMockModel


class OfflineWeatherModelTests(unittest.TestCase):
    def setUp(self):
        self.model = OfflineMockModel()

    def test_routes_explicit_chinese_city_to_weather_tool(self):
        response = self.model.generate(
            {"user_message": "深圳今天天气怎样？"}
        )

        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(
            response.tool_calls[0].name,
            "weather.get_current",
        )
        self.assertEqual(
            response.tool_calls[0].arguments,
            {"location": "深圳"},
        )

    def test_routes_paraphrased_people_question(self):
        response = self.model.generate(
            {"user_message": "摄像头里面现在站着几位？"}
        )

        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(
            response.tool_calls[0].name,
            "vision.get_people_count",
        )

    def test_formats_successful_weather_result(self):
        response = self.model.generate(
            {
                "user_message": "深圳天气",
                "recent_tool_results": [
                    {
                        "tool_name": "weather.get_current",
                        "status": "SUCCEEDED",
                        "result": {
                            "location": {
                                "name": "深圳",
                                "admin1": "广东",
                                "country": "中国",
                            },
                            "current": {
                                "condition": "partly cloudy",
                                "temperature_c": 31.0,
                                "apparent_temperature_c": 36.0,
                                "relative_humidity_percent": 70,
                                "precipitation_mm": 0.0,
                                "wind_speed_kmh": 9.5,
                            },
                        },
                    }
                ],
            }
        )

        self.assertIn("深圳", response.content)
        self.assertIn("31.0°C", response.content)
        self.assertEqual(response.tool_calls, [])


if __name__ == "__main__":
    unittest.main()
