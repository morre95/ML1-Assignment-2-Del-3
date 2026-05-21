import pytest

from react_agent_system.tools import research


class FakeResponse:
    def __init__(self, payload: dict, status_error: Exception | None = None) -> None:
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self) -> None:
        if self.status_error is not None:
            raise self.status_error

    def json(self) -> dict:
        return self.payload


def test_weather_lookup_returns_current_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_get(url: str, params: dict[str, object], timeout: int) -> FakeResponse:
        calls.append((url, params, timeout))
        if url == research.OPEN_METEO_GEOCODING_URL:
            return FakeResponse(
                {
                    "results": [
                        {
                            "name": "Stockholm",
                            "admin1": "Stockholm County",
                            "country": "Sweden",
                            "latitude": 59.3293,
                            "longitude": 18.0686,
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "current": {
                    "time": "2026-05-21T12:00",
                    "temperature_2m": 17.5,
                    "relative_humidity_2m": 62,
                    "apparent_temperature": 16.8,
                    "precipitation": 0.0,
                    "weather_code": 2,
                    "wind_speed_10m": 11.2,
                },
                "current_units": {
                    "temperature_2m": "\u00b0C",
                    "relative_humidity_2m": "%",
                    "apparent_temperature": "\u00b0C",
                    "precipitation": "mm",
                    "wind_speed_10m": "km/h",
                },
            }
        )

    monkeypatch.setattr(research.requests, "get", fake_get)

    result = research.weather_lookup("Stockholm")

    assert "Current weather for Stockholm, Stockholm County, Sweden" in result
    assert "- Condition: Partly cloudy" in result
    assert "- Temperature: 17.5 \u00b0C" in result
    assert "- Humidity: 62 %" in result
    assert calls[0][1]["name"] == "Stockholm"
    assert calls[1][1]["latitude"] == 59.3293


def test_weather_lookup_handles_missing_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        research.requests,
        "get",
        lambda url, params, timeout: FakeResponse({"results": []}),
    )

    assert research.weather_lookup("missing") == "No weather location found."


def test_weather_lookup_rejects_empty_location() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        research.weather_lookup(" ")
