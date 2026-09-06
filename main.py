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

    headers = {"User-Agent": "PilskieAEDBot/1.0 (kontakt@pgrm.pl)"}

    # 1. Geokodowanie adresu
    lat, lon = None, None
    try:
        geo_res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "pl"},
            headers=headers, timeout=3.0
        ).json()
        if geo_res:
            lat = float(geo_res[0]["lat"])
            lon = float(geo_res[0]["lon"])
    except Exception:
        pass

    # Fallback: jeśli nie znalazł dokładnego numeru (np. Lelewela 140), szukaj po samej ulicy i mieście
    if lat is None:
        try:
            # Uproszczenie adresu: usuwamy zbędne słowa i bierzemy tylko główne człony
            geo_res = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{address}, Polska", "format": "json", "limit": 1},
                headers=headers, timeout=2.5
            ).json()
            if geo_res:
                lat = float(geo_res[0]["lat"])
                lon = float(geo_res[0]["lon"])
        except Exception:
            pass

    if lat is None:
        return {"status": "not_found", "message": f"Nie udało się ustalić współrzędnych dla adresu: {address}"}

    # 2. Szukamy AED w promieniu 5000 metrów (5 km), obejmującym całą okolicę
    query = f"""[out:json][timeout:5];nwr["emergency"="defibrillator"](around:5000,{lat},{lon});out center;"""
    overpass_urls = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass-api.de/api/interpreter"
    ]

    elements = []
    for url in overpass_urls:
        try:
            op_res = requests.get(url, params={"data": query}, headers=headers, timeout=4.0)
            if op_res.status_code == 200:
                elements = op_res.json().get("elements", [])
                if elements:
                    break
        except Exception:
            continue

    if not elements:
        return {
            "status": "not_found",
            "message": f"Brak zarejestrowanego AED w promieniu 5 km od współrzędnych ({round(lat, 4)}, {round(lon, 4)})."
        }

    # 3. Parsowanie i wyliczanie odległości
    parsed_aeds = []
    for el in elements:
        t_lat = el.get("lat") or el.get("center", {}).get("lat")
        t_lon = el.get("lon") or el.get("center", {}).get("lon")
        if t_lat and t_lon:
            dist = calculate_distance(lat, lon, float(t_lat), float(t_lon))
            parsed_aeds.append((dist, el))

    if not parsed_aeds:
        return {"status": "not_found", "message": "Brak precyzyjnych współrzędnych AED."}

    # Wybór najbliższego AED
    nearest_dist, nearest_elem = min(parsed_aeds, key=lambda x: x[0])
    tags = nearest_elem.get("tags", {})

    # Wyciągamy jak najwięcej konkretnych informacji o miejscu
    nazwa_obiektu = tags.get("name") or tags.get("operator") or ""
    miejsce_montazu = tags.get("defibrillator:location") or tags.get("description") or "na ścianie budynku"
    dostep = tags.get("access") or ""
    
    opis = f"{nazwa_obiektu}, {miejsce_montazu}".strip(", ")
    if dostep and dostep != "yes":
        opis += f" (dostęp: {dostep})"

    return {
        "status": "success",
        "odleglosc_metry": nearest_dist,
        "lokalizacja": opis or "przy wejściu głównym"
    }
