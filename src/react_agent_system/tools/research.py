"""Research tool implementations."""

from __future__ import annotations

from typing import Any

import requests
import wikipedia
from duckduckgo_search import DDGS

OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_TIMEOUT_SECONDS = 20
WEATHER_CODE_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
}


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return compact text results."""

    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    rows: list[str] = []
    with DDGS() as ddgs:
        for result in ddgs.text(query, max_results=max_results):
            title = result.get("title", "Untitled")
            href = result.get("href", "")
            body = result.get("body", "")
            rows.append(f"- {title}\n  {href}\n  {body}")

    return "\n".join(rows) if rows else "No web search results found."


def weather_lookup(location: str) -> str:
    """Look up current weather for a location using Open-Meteo."""

    if not location.strip():
        raise ValueError("Weather location cannot be empty.")

    geocoding_data = _get_json(
        OPEN_METEO_GEOCODING_URL,
        params={
            "name": location,
            "count": 1,
            "language": "en",
            "format": "json",
        },
    )
    results = geocoding_data.get("results", [])
    if not isinstance(results, list) or not results:
        return "No weather location found."

    place = results[0]
    latitude = place.get("latitude")
    longitude = place.get("longitude")
    if latitude is None or longitude is None:
        return "No weather location found."

    forecast_data = _get_json(
        OPEN_METEO_FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,wind_speed_10m"
            ),
            "timezone": "auto",
        },
    )
    return _format_weather(place, forecast_data)


def wikipedia_lookup(query: str, sentences: int = 5) -> str:
    """Look up a topic on Wikipedia."""

    if not query.strip():
        raise ValueError("Wikipedia query cannot be empty.")

    try:
        page_title = wikipedia.search(query, results=1)[0]
        return wikipedia.summary(page_title, sentences=sentences, auto_suggest=False)
    except IndexError:
        return "No Wikipedia page found."
    except wikipedia.DisambiguationError as exc:
        options = ", ".join(exc.options[:5])
        return f"Query is ambiguous. Top options: {options}"
    except wikipedia.PageError:
        return "No Wikipedia page found."


def _get_json(url: str, params: dict[str, object]) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=WEATHER_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise ValueError(f"Weather request failed: {exc}") from exc
    except ValueError as exc:
        raise ValueError("Weather service returned invalid JSON.") from exc

    if not isinstance(data, dict):
        raise ValueError("Weather service returned an unexpected response.")
    return data


def _format_weather(place: dict[str, Any], forecast_data: dict[str, Any]) -> str:
    current = forecast_data.get("current", {})
    units = forecast_data.get("current_units", {})
    if not isinstance(current, dict) or not isinstance(units, dict):
        raise ValueError("Weather service response is missing current weather data.")

    weather_code = current.get("weather_code")
    condition = WEATHER_CODE_DESCRIPTIONS.get(weather_code, f"Weather code {weather_code}")
    place_name = _format_place_name(place)
    return "\n".join(
        [
            f"Current weather for {place_name}",
            f"- Condition: {condition}",
            f"- Temperature: {_format_value(current, units, 'temperature_2m')}",
            f"- Feels like: {_format_value(current, units, 'apparent_temperature')}",
            f"- Humidity: {_format_value(current, units, 'relative_humidity_2m')}",
            f"- Precipitation: {_format_value(current, units, 'precipitation')}",
            f"- Wind speed: {_format_value(current, units, 'wind_speed_10m')}",
            f"- Time: {current.get('time', 'unknown')}",
        ]
    )


def _format_place_name(place: dict[str, Any]) -> str:
    parts = [
        str(place.get("name") or "").strip(),
        str(place.get("admin1") or "").strip(),
        str(place.get("country") or "").strip(),
    ]
    return ", ".join(part for part in parts if part) or "requested location"


def _format_value(current: dict[str, Any], units: dict[str, Any], key: str) -> str:
    value = current.get(key)
    unit = units.get(key, "")
    if value is None:
        return "unknown"
    return f"{value} {unit}".strip()
