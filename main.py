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

@app.get("/")
def health_check():
    return {"status": "alive"}

@app.post("/find-aed")
async def find_aed(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"status": "error", "message": "Błędne dane wejściowe"}
    
    address = None
    if "args" in body and isinstance(body["args"], dict):
        address = body["args"].get("address")
    elif "address" in body:
        address = body.get("address")

    if not address:
        return {"status": "error", "message": "Brak adresu w zapytaniu"}

    headers = {"User-Agent": "MedycznyBotTreningowy/1.0 (kontakt@pgrm.pl)"}

    # 1. Geokodowanie adresu (szukanie w Polsce)
    try:
        geo_res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "pl"},
            headers=headers, timeout=2.5
        ).json()
        if not geo_res:
            return {"status": "not_found", "message": f"Nie znaleziono w bazie adresu: {address}"}
        lat, lon = float(geo_res[0]["lat"]), float(geo_res[0]["lon"])
    except Exception:
        return {"status": "timeout", "message": "Wyszukiwanie adresu trwa zbyt długo. Prowadź RKO."}

    # 2. Szukamy Node, Way i Relation (nwr) w promieniu 2500m z wyliczeniem środka (out center)
    query = f"""[out:json][timeout:4];nwr["emergency"="defibrillator"](around:2500,{lat},{lon});out center;"""
    overpass_urls = [
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass-api.de/api/interpreter"
    ]

    elements = []
    for url in overpass_urls:
        try:
            op_res = requests.get(url, params={"data": query}, headers=headers, timeout=3.5)
            if op_res.status_code == 200:
                elements = op_res.json().get("elements", [])
                if elements:
                    break
        except Exception:
            continue

    if not elements:
        return {
            "status": "not_found",
            "message": "Brak zarejestrowanego defibrylatora AED w promieniu 2.5 km."
        }

    # 3. Wyciągnięcie współrzędnych (dla punktów lub centrów budynków)
    parsed_aeds = []
    for el in elements:
        t_lat = el.get("lat") or el.get("center", {}).get("lat")
        t_lon = el.get("lon") or el.get("center", {}).get("lon")
        if t_lat and t_lon:
            dist = calculate_distance(lat, lon, float(t_lat), float(t_lon))
            parsed_aeds.append((dist, el))

    if not parsed_aeds:
        return {"status": "not_found", "message": "Brak precyzyjnych współrzędnych AED w pobliżu."}

    # Wybór najbliższego
    nearest_dist, nearest_elem = min(parsed_aeds, key=lambda x: x[0])
    tags = nearest_elem.get("tags", {})

    location_desc = (
        tags.get("defibrillator:location") or 
        tags.get("description") or 
        tags.get("operator") or 
        tags.get("name") or 
        "przy wejściu głównym do obiektu"
    )

    return {
        "status": "success",
        "odleglosc_metry": nearest_dist,
        "lokalizacja": location_desc
    }
