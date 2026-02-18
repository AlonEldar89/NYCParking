"""FastAPI backend for NYC street cleaning parking finder."""

import time
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pyproj import Transformer

from backend.parser import parse_sign_description
from backend.scheduler import hours_until_next_cleaning

app = FastAPI(title="NYC Parking Finder")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SODA_URL = "https://data.cityofnewyork.us/resource/nfid-uabd.json"
SODA_BASE = (
    "$where=sign_description like '%25SANITATION BROOM SYMBOL%25'"
    "&$select=on_street,from_street,to_street,side_of_street,borough,"
    "sign_description,sign_x_coord,sign_y_coord"
    "&$order=:id"
)
PAGE_SIZE = 50000

# NY State Plane (ft) -> WGS84
transformer = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)


@dataclass
class CachedData:
    signs: list[dict]
    fetched_at: float = 0.0


_cache = CachedData(signs=[])
CACHE_TTL = 3600  # 1 hour


async def _fetch_signs() -> list[dict]:
    now = time.time()
    if _cache.signs and (now - _cache.fetched_at) < CACHE_TTL:
        return _cache.signs

    raw = []
    async with httpx.AsyncClient(timeout=60) as client:
        offset = 0
        while True:
            resp = await client.get(
                f"{SODA_URL}?{SODA_BASE}&$limit={PAGE_SIZE}&$offset={offset}"
            )
            resp.raise_for_status()
            page = resp.json()
            if not page:
                break
            raw.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

    signs = []
    for row in raw:
        x = row.get("sign_x_coord")
        y = row.get("sign_y_coord")
        if not x or not y:
            continue
        try:
            lng, lat = transformer.transform(float(x), float(y))
        except Exception:
            continue

        schedule = parse_sign_description(row.get("sign_description", ""))
        if schedule is None:
            continue

        signs.append({
            "on_street": row.get("on_street", ""),
            "from_street": row.get("from_street", ""),
            "to_street": row.get("to_street", ""),
            "side": row.get("side_of_street", ""),
            "borough": row.get("borough", ""),
            "description": row.get("sign_description", ""),
            "lat": lat,
            "lng": lng,
            "schedule": schedule,
        })

    _cache.signs = signs
    _cache.fetched_at = time.time()
    return signs


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@app.get("/api/streets")
async def get_streets(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius_km: float = Query(0.5, description="Search radius in km"),
):
    signs = await _fetch_signs()

    segments: dict[tuple, dict] = {}
    for s in signs:
        dist = _haversine_km(lat, lng, s["lat"], s["lng"])
        if dist > radius_km:
            continue

        key = (s["on_street"], s["from_street"], s["to_street"], s["side"])
        if key not in segments:
            hrs = hours_until_next_cleaning(s["schedule"])
            if hrs == float("inf"):
                hrs = 999.0
            segments[key] = {
                "on_street": s["on_street"],
                "from_street": s["from_street"],
                "to_street": s["to_street"],
                "side": s["side"],
                "borough": s["borough"],
                "description": s["description"],
                "hours_until_cleaning": round(hrs, 1),
                "coords": [],
            }
        segments[key]["coords"].append([s["lat"], s["lng"]])

    results = []
    for seg in segments.values():
        coords = seg.pop("coords")
        if len(coords) >= 2:
            coords.sort(key=lambda c: (c[0], c[1]))
            seg["start"] = coords[0]
            seg["end"] = coords[-1]
        else:
            seg["start"] = coords[0]
            seg["end"] = coords[0]
        results.append(seg)

    results.sort(key=lambda r: r["hours_until_cleaning"], reverse=True)
    return results[:500]


@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")
