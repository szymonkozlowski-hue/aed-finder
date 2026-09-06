import json
import math
import os
import requests
from fastapi import FastAPI, Request

app = FastAPI()

def calculate_distance(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return int(r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

JSON_PATH = "aed_poland.json"
ALL_AEDS = []

def load_local_aeds():
    global ALL_AEDS
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                ALL_AEDS = json.load(f)
        except Exception:
            pass

# Wczytanie bazy przy starcie
load_local_aeds()

@app.get("/")
def health():
    return {
        "status": "ok",
        "total_aeds_loaded": len(ALL_AEDS),
        "instrukcja": "Wejdz na /pobierz-baze aby jednorazowo pobrac 17k punktow z Polski."
    }

# Specjalny endpoint, który sam pobierze dane w chmurze
@app.get("/pobierz-baze")
def pobierz_baze():
    global ALL_AEDS
    query = """
    [out:json][timeout:90];
    area["ISO3166-1"="PL"][admin_level=2]->.polska;
    (
      nwr["emergency"="defibrillator"](area.polska);
    );
    out center tags;
    """
    url = "https://overpass-api.de/api/interpreter"
    headers = {"User-Agent": "PobieraczAED_Trening/1.0"}
    
    try:
        res = requests.post(url, data={"data": query}, headers=headers, timeout=120)
        elements = res.json().get("elements", [])
        
        cleaned = []
        for el in elements:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if not lat or not lon:
                continue
            
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("operator") or ""
            location = tags.get("defibrillator:location") or tags.get("description") or ""
            access = tags.get("access") or ""
            
            parts = [p for p in [name, location] if p]
            desc = ", ".join(parts) if parts else "przy wejściu głównym do obiektu"
            
            if access and access not in ["yes", "public"]:
                desc += f" (dostęp: {access})"
                
            cleaned.append({
                "lat": round(float(lat), 5),
                "lon": round(float(lon), 5),
                "desc": desc
            })
            
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False)
            
        ALL_AEDS = cleaned
        return {"status": "sukces", "pobranych_urzadzen": len(cleaned)}
    except Exception as e:
        return {"status": "blad", "komunikat": str(e)}

@app.post("/find-aed")
async def find_aed(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"status": "error", "message": "Błędne dane"}

    address = None
    if "args" in body and isinstance(body["args"], dict):
        address = body["args"].get("address")
    elif "address" in body:
        address = body.get("address")

    if not address:
        return {"status": "error", "message": "Brak adresu"}

    # 1. Błyskawiczne geokodowanie adresu
    headers = {"User-Agent": "MedycznyBotTreningowy/1.0"}
    lat, lon = None, None
    try:
        geo = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "pl"},
            headers=headers, timeout=2.0
        ).json()
        if geo:
            lat = float(geo[0]["lat"])
            lon = float(geo[0]["lon"])
    except Exception:
        pass

    if lat is None:
        return {
            "status": "not_found",
            "message": "Nie udało się ustalić współrzędnych. Skup się na uciskaniu klatki piersiowej."
        }

    if not ALL_AEDS:
        return {"status": "error", "message": "Baza AED jest pusta. Wejdz na /pobierz-baze."}

    # 2. Szybkie przefiltrowanie okolicy (+/- 0.08 stopnia to ok. 8-9 km)
    lat_min, lat_max = lat - 0.08, lat + 0.08
    lon_min, lon_max = lon - 0.12, lon + 0.12

    local_candidates = [
        aed for aed in ALL_AEDS 
        if lat_min <= aed["lat"] <= lat_max and lon_min <= aed["lon"] <= lon_max
    ]

    pool = local_candidates if local_candidates else ALL_AEDS

    # Wybór najbliższego
    nearest = min(pool, key=lambda aed: calculate_distance(lat, lon, aed["lat"], aed["lon"]))
    dist = calculate_distance(lat, lon, nearest["lat"], nearest["lon"])

    return {
        "status": "success",
        "odleglosc_metry": dist,
        "lokalizacja": nearest["desc"]
    }
