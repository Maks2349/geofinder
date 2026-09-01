import requests
import urllib.parse
import re
from typing import Optional, Dict, Any

def clean_place_query(text: str) -> str:
    t = text.strip()
    t = re.sub(r'^(w|we|okolice|gmina|powiat|pobliże)\s+', '', t, flags=re.IGNORECASE)
    return t.strip()

def geocode_street_address(street: str, city: str = "", country: str = "Polska") -> Optional[Dict[str, Any]]:
    """
    Błyskawiczne geokodowanie ulicy w OpenStreetMap (timeout 1.5s).
    """
    clean_s = clean_place_query(street)
    clean_c = clean_place_query(city)
    
    query = f"{clean_s}, {clean_c}, {country}" if clean_s and clean_c else (clean_s or street or city)
    if not query:
        return None

    headers = {
        "User-Agent": "GeoFinder-Fast/4.0 (contact: geofinder@app.local)"
    }

    try:
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit=1&addressdetails=1"
        res = requests.get(url, headers=headers, timeout=1.8)
        if res.status_code == 200:
            data = res.json()
            if data and len(data) > 0:
                item = data[0]
                return {
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "display_name": item.get("display_name", "")
                }
    except Exception:
        pass

    return None
