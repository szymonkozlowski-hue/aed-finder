import math
import requests
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class AddressRequest(BaseModel):
    address: str

def calculate_distance(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return int(r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

@app.post("/find-aed")
def find_aed(req: AddressRequest):
    headers = {"User-Agent": "MedycznyBotTreningowy/1.0"}
    
    # 1. Sprawdzenie współrzędnych adresu
    geo_res = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": req.address, "format": "json", "limit": 1, "countrycodes": "pl"},
        headers=headers, timeout=5
    ).json()

    if not geo_res:
        return {"status": "error", "message": "Nie rozpoznano adresu."}

    lat, lon = float(geo_res[0]["lat"]), float(geo_res[0]["lon"])

    # 2. Szukanie AED w promieniu 1 km
    query = f"""[out:json][timeout:5];(node["emergency"="defibrillator"](around:1000,{lat},{lon}););out body;"""
    overpass_res = requests.get(
        "https://overpass-api.de/api/interpreter",
        params={"data": query}, headers=headers, timeout=8
    )
    
    if overpass_res.status_code != 200:
        return {"status": "error", "message": "Baza mapy chwilowo nie odpowiada."}

    elements = overpass_res.json().get("elements", [])
    if not elements:
        return {"status": "not_found", "message": "Brak zarejestrowanego AED w pobliżu."}

    # 3. Wybór najbliższego AED
    nearest = min(elements, key=lambda x: calculate_distance(lat, lon, x["lat"], x["lon"]))
    distance = calculate_distance(lat, lon, nearest["lat"], nearest["lon"])
    tags = nearest.get("tags", {})
    
    location_desc = tags.get("defibrillator:location") or tags.get("description") or "Przy wejściu głównym do budynku"

    return {
        "status": "success",
        "odleglosc_metry": distance,
        "lokalizacja": location_desc
    }
