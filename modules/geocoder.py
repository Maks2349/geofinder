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
    Precyzyjne geokodowanie ulicy i numeru w OpenStreetMap.
    """
    clean_s = clean_place_query(street)
    clean_c = clean_place_query(city)
    
    queries = []
    if clean_s and clean_c:
        queries.append(f"{clean_s}, {clean_c}, {country}")
    if clean_s:
        queries.append(f"{clean_s}, {country}")
    if clean_c:
        queries.append(f"{clean_c}, {country}")
    if street:
        queries.append(f"{street}, {country}")

    headers = {
        "User-Agent": "GeoFinder-Street-Precision/4.0 (contact: geofinder@app.local)"
    }

    for q in queries:
        try:
            url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(q)}&format=json&limit=1&addressdetails=1"
            res = requests.get(url, headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json()
                if data and len(data) > 0:
                    item = data[0]
                    return {
                        "lat": float(item["lat"]),
                        "lon": float(item["lon"]),
                        "display_name": item.get("display_name", ""),
                        "road": item.get("address", {}).get("road", clean_s)
                    }
        except Exception:
            continue

    return None
