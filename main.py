import math
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

# Pamięć podręczna na defibrylatory
AED_CACHE = []

def refresh_aed_cache():
    global AED_CACHE
    url = "https://overpass.private.coffee/api/interpreter"
    # Pobieramy defibrylatory w Polsce raz przy starcie (obszar wielkopolski i okolic)
    query = """
    [out:json][timeout:25];
    area["ISO3166-1"="PL"]->.poland;
    nwr["emergency"="defibrillator"](area.poland);
    out center;
    """
    try:
        res = requests.get(url, params={"data": query}, headers={"User-Agent": "MedycznyBotTreningowy/1.0"}, timeout=20)
        if res.status_code == 200:
            data = res.json().get("elements", [])
            parsed = []
            for el in data:
                lat = el.get("lat") or el.get("center", {}).get("lat")
                lon = el.get("lon") or el.get("center", {}).get("lon")
                if lat and lon:
                    tags = el.get("tags", {})
                    name = tags.get("name") or tags.get("operator") or ""
                    loc = tags.get("defibrillator:location") or tags.get("description") or "przy wejściu"
                    parsed.append({
                        "lat": float(lat),
                        "lon": float(lon),
                        "desc": f"{name}, {loc}".strip(", ")
                    })
            if parsed:
                AED_CACHE = parsed
    except Exception:
        pass

@app.on_event("startup")
def startup_event():
    refresh_aed_cache()

@app.get("/")
def health():
    return {"status": "ok", "cached_aeds": len(AED_CACHE)}

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

    # 1. Geokodowanie z bardzo krótkim limitem (max 2 sekundy)
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
            "status": "timeout",
            "message": "Nie udało się ustalić współrzędnych. Skup się na uciskaniu klatki piersiowej."
        }

    # 2. Błyskawiczne przeszukanie lokalnej pamięci (trwa < 5 ms)
    if not AED_CACHE:
        # Fallback jeśli cache się nie załadował
        refresh_aed_cache()

    candidates = []
    for item in AED_CACHE:
        dist = calculate_distance(lat, lon, item["lat"], item["lon"])
        if dist <= 4000: # szukamy w promieniu 4 km
            candidates.append((dist, item))

    if not candidates:
        return {
            "status": "not_found",
            "message": "Brak zarejestrowanego AED w promieniu 4 km."
        }

    candidates.sort(key=lambda x: x[0])
    best_dist, best_aed = candidates[0]

    return {
        "status": "success",
        "odleglosc_metry": best_dist,
        "lokalizacja": best_aed["desc"]
    }
