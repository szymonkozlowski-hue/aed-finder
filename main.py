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
    headers = {"User-Agent": "MedycznyBotTreningowy/1.0 (kontakt@pgrm.pl)"}
    
    # 1. Błyskawiczne geokodowanie (timeout 3s)
    try:
        geo_res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": req.address, "format": "json", "limit": 1, "countrycodes": "pl"},
            headers=headers, timeout=3
        ).json()
    except Exception:
        return {"status": "error", "message": "Brak odpowiedzi geokodera."}

    if not geo_res:
        return {"status": "error", "message": "Nie znaleziono adresu."}

    lat, lon = float(geo_res[0]["lat"]), float(geo_res[0]["lon"])

    # 2. Szybkie zapytanie Overpass (używamy szybkiego serwera Kumi Systems i promienia 600m)
    query = f"""[out:json][timeout:4];node["emergency"="defibrillator"](around:600,{lat},{lon});out body;"""
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
        return {"status": "not_found", "message": "Brak AED w promieniu 600m."}

    # 3. Wybór najbliższego
    nearest = min(elements, key=lambda x: calculate_distance(lat, lon, x["lat"], x["lon"]))
    distance = calculate_distance(lat, lon, nearest["lat"], nearest["lon"])
    tags = nearest.get("tags", {})
    
    location_desc = tags.get("defibrillator:location") or tags.get("description") or tags.get("operator") or "przy głównym wejściu"

    return {
        "status": "success",
        "odleglosc_metry": distance,
        "lokalizacja": location_desc
    }
