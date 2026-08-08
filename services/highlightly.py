import os
import httpx
from fastapi import HTTPException

HIGHLIGHTLY_KEY = os.environ.get("HIGHLIGHTLY_KEY")

BASE_URL = "https://soccer.highlightly.net"


async def highlightly_get(path: str, params: dict | None = None):
    if not HIGHLIGHTLY_KEY:
        raise HTTPException(
            status_code=500,
            detail="HIGHLIGHTLY_KEY غير موجود"
        )

    headers = {
        "x-rapidapi-key": HIGHLIGHTLY_KEY,
        "x-rapidapi-host": "soccer.highlightly.net"
    }

    url = BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            url,
            headers=headers,
            params=params or {}
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    return response.json()


async def get_saudi_matches(season: int = 2026):
    return await highlightly_get(
        "/matches",
        {
            "leagueName": "Saudi Pro League",
            "season": season
        }
    )
