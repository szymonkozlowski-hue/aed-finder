import math
import requests
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI()

def calculate_distance(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return int(r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

@app.post("/find-aed")
async def find_aed(request: Request):
    body = await request.json()
    
    # Obsługa formatu Retell (args.address) lub formatu bezpośredniego (address)
    address = None
    if "args" in body and isinstance(body["args"], dict):
        address = body["args"].get("address")
    elif "address" in body:
        address = body.get("address")

    if not address:
        return {"status": "error", "message": "Nie przekazano adresu zdarzenia."}

    headers = {"User-Agent": "MedycznyBotTreningowy/1.0 (kontakt@pgrm.pl)"}

    # 1. Geokodowanie adresu
    try:
        geo_res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "pl"},
            headers=headers, timeout=3
        ).json()
    except Exception:
        return {"status": "error", "message": "Brak odpowiedzi geokodera."}

    if not geo_res:
        return {"status": "error", "message": f"Nie znaleziono w bazie adresu: {address}"}

    lat, lon = float(geo_res[0]["lat"]), float(geo_res[0]["lon"])

    # 2. Zapytanie o AED w promieniu 1200m
    query = f"""[out:json][timeout:4];node["emergency"="defibrillator"](around:1200,{lat},{lon});out body;"""
    overpass_urls = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass-api.de/api/interpreter"
    ]

    elements = []
    for url in overpass_urls:
        try:
            op_res = requests.get(url, params={"data": query}, headers=headers, timeout=4)
            if op_res.status_code == 200:
                elements = op_res.json().get("elements", [])
                break
        except Exception:
            continue

    if not elements:
        return {
            "status": "not_found",
            "message": "Brak zarejestrowanego defibrylatora AED w promieniu 1.2 km."
        }

    # 3. Wybór najbliższego AED
    nearest = min(elements, key=lambda x: calculate_distance(lat, lon, x["lat"], x["lon"]))
    distance = calculate_distance(lat, lon, nearest["lat"], nearest["lon"])
    tags = nearest.get("tags", {})

    location_desc = (
        tags.get("defibrillator:location") or 
        tags.get("description") or 
        tags.get("operator") or 
        "przy wejściu głównym do obiektu"
    )

    return {
        "status": "success",
        "odleglosc_metry": distance,
        "lokalizacja": location_desc
    }
