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

load_local_aeds()

@app.get("/")
def health():
    return {
        "status": "ok",
        "total_aeds_loaded": len(ALL_AEDS),
        "instrukcja": "Wejdz na /pobierz-baze aby pobrac oficjalna baze OpenAEDMap."
    }

@app.get("/pobierz-baze")
def pobierz_baze():
    global ALL_AEDS
    # Oficjalne, bezposrednie zrodlo ze Stowarzyszenia OpenStreetMap Polska
    url = "https://openaedmap.org/api/v1/countries/PL.geojson"
    headers = {"User-Agent": "MedycznyBotTreningowy/1.0"}
    
    try:
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code != 200:
            return {"status": "blad", "komunikat": f"Serwer OpenAED odpowiedzial kodem {res.status_code}"}
            
        data = res.json()
        features = data.get("features", [])
        
        cleaned = []
        for feat in features:
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            # W GeoJSON kolejnosc to [lon, lat]
            if len(coords) >= 2:
                lon, lat = float(coords[0]), float(coords[1])
                props = feat.get("properties", {})
                
                name = props.get("operator") or props.get("name") or ""
                loc = props.get("defibrillator:location") or props.get("description") or ""
                access = props.get("access") or ""
                
                parts = [p for p in [name, loc] if p]
                desc = ", ".join(parts) if parts else "w obiekcie publicznym"
                
                if access and access not in ["yes", "public"]:
                    desc += f" (dostęp: {access})"
                    
                cleaned.append({
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
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

    # 1. Geokodowanie adresu
    headers = {"User-Agent": "MedycznyBotTreningowy/1.0"}
    lat, lon = None, None
    try:
        geo = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "pl"},
            headers=headers, timeout=2.5
        ).json()
        if geo:
            lat = float(geo[0]["lat"])
            lon = float(geo[0]["lon"])
    except Exception:
        pass

    if lat is None:
        return {
            "status": "not_found",
            "message": "Nie udało się zlokalizować adresu w bazie. Prowadź RKO."
        }

    if not ALL_AEDS:
        return {"status": "error", "message": "Baza AED nie jest zaladowana."}

    # 2. Szukamy wyłacznie w promieniu maksymalnie 2.5 km (dla pieszych/samochodu to rozsądny dystans)
    # Wstępna siatka: +/- 0.03 stopnia (~2.5-3 km)
    lat_min, lat_max = lat - 0.035, lat + 0.035
    lon_min, lon_max = lon - 0.045, lon + 0.045

    local_candidates = [
        aed for aed in ALL_AEDS 
        if lat_min <= aed["lat"] <= lat_max and lon_min <= aed["lon"] <= lon_max
    ]

    # Obliczamy odległości
    nearby_list = []
    for aed in local_candidates:
        dist = calculate_distance(lat, lon, aed["lat"], aed["lon"])
        if dist <= 2500:  # Tylko urządzenia do 2,5 km
            nearby_list.append((dist, aed))

    if not nearby_list:
        return {
            "status": "not_found",
            "message": "Brak defibrylatora AED w bezpośrednim zasięgu (promień 2,5 km). Skup się na uciskaniu klatki piersiowej."
        }

    nearby_list.sort(key=lambda x: x[0])
    best_dist, best_aed = nearby_list[0]

    return {
        "status": "success",
        "odleglosc_metry": best_dist,
        "lokalizacja": best_aed["desc"]
    }
