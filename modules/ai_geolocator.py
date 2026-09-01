import os
import json
import base64
import re
import time
import requests
from typing import Dict, Any, Optional, List, Union
from io import BytesIO
from PIL import Image, ImageEnhance, ImageOps, ExifTags

try:
    from google import genai
    from google.genai import types
    GENAI_SDK_AVAILABLE = True
except ImportError:
    GENAI_SDK_AVAILABLE = False

HYPER_PARK_OSINT_PROMPT = """Jesteś Arcymistrzem GeoGuessr, ekspertem wywiadu jawnoźródłowego (OSINT) oraz analitykiem topografii. 
Otrzymujesz GŁÓWNE ZDJĘCIE oraz 4 WYCINKI (efekt lupy/mikroskopu na rogi zdjęcia), byś mógł odczytać mikroskopijne teksty.
Masz dostęp do WYSZUKIWARKI GOOGLE (Google Search Grounding). Użyj jej do weryfikacji adresów!

{USER_HINT_SECTION}

KROKI DEDUKCJI:
0. LUPA I OCR: Przeanalizuj wycinki pod kątem najmniejszych tekstów, szyldów, tablic. Użyj wyszukiwarki do sprawdzenia odczytanych nazw!
1. INFRASTRUKTURA: Słupki, krawężniki, latarnie, znaki.
2. ARCHITEKTURA I NATURA: Kształt dachów, góry, drzewa.

WAŻNE: Jeśli rozpoznasz dokładny budynek, sklep, górę lub obiekt, wpisz zapytanie do pola "search_map_query" (np. "Kościół Mariacki, Kraków" lub "Stacja Orlen, Zakopane"). Nasz skrypt pobierze wtedy GPS idealnie z dachu budynku!

Format WYLACZNIE JSON:
```json
{
  "deduction_steps": "Opis",
  "search_map_query": "Zapytanie do bazy map (zostaw puste jeśli brak)",
  "candidates": [
    {
      "rank": 1,
      "probability": 95,
      "exact_street": "Ulica",
      "place_name": "Obiekt",
      "city": "Miasto",
      "region": "Woj.",
      "country": "Kraj",
      "latitude": 52.2,
      "longitude": 21.0,
      "reason": "Dowód"
    }
  ],
  "heading_degrees": 180,
  "suggested_hashtags": [],
  "geoguessr": {}
}
```"""

def _extract_gps_from_exif(image: Image.Image) -> Optional[Dict[str, float]]:
    try:
        exif = image.getexif()
        if not exif: return None
        gps_info = None
        for key, val in exif.items():
            if ExifTags.TAGS.get(key) == 'GPSInfo':
                gps_info = val
                break
        if not gps_info: return None
        
        def convert_to_degrees(value):
            d, m, s = value
            return float(d) + (float(m) / 60.0) + (float(s) / 3600.0)
            
        lat = convert_to_degrees(gps_info[2])
        if gps_info[1] != 'N': lat = -lat
        lon = convert_to_degrees(gps_info[4])
        if gps_info[3] != 'E': lon = -lon
        return {"lat": lat, "lon": lon}
    except Exception:
        return None

def reverse_geocode_nominatim(lat: float, lon: float) -> Dict[str, Any]:
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&accept-language=pl"
    headers = {"User-Agent": "GeoFinderAI_App_OSINT"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            address = data.get("address", {})
            return {
                "place_name": data.get("name") or data.get("display_name", "Nieznana lokalizacja").split(",")[0],
                "exact_street": address.get("road", "") + (" " + address.get("house_number", "") if address.get("house_number") else ""),
                "city": address.get("city", address.get("town", address.get("village", ""))),
                "region": address.get("state", ""),
                "country": address.get("country", "Polska"),
            }
    except Exception:
        pass
    return {"place_name": "Znaleziono po EXIF GPS", "exact_street": "Dokładny GPS", "city": "", "region": "", "country": "Polska"}

def search_map_database(query: str) -> Optional[Dict[str, Any]]:
    if not query or len(query.strip()) < 3:
        return None
    url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(query)}&format=json&limit=1&accept-language=pl"
    headers = {"User-Agent": "GeoFinderAI_App_OSINT"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            results = r.json()
            if results and len(results) > 0:
                match = results[0]
                return {
                    "lat": float(match["lat"]),
                    "lon": float(match["lon"]),
                    "name": match.get("name", query),
                    "type": match.get("type", "")
                }
    except Exception:
        pass
    return None

def _extract_and_repair_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match: raw = match.group(1).strip()
    else:
        start, end = text.find('{'), text.rfind('}')
        raw = text[start:end+1] if start != -1 and end > start else text
    try:
        data = json.loads(raw)
        if "candidates" in data and len(data["candidates"]) > 0: return data
    except Exception: pass
    try:
        cleaned = re.sub(r",\s*([\]}])", r"\1", raw)
        data = json.loads(cleaned)
        if "candidates" in data and len(data["candidates"]) > 0: return data
    except Exception: pass
    return {
        "deduction_steps": "Błąd AI.",
        "search_map_query": "",
        "candidates": [{"rank": 1, "probability": 10, "exact_street": "Błąd", "place_name": "Błąd", "city": "?", "region": "?", "country": "Polska", "latitude": 52.069, "longitude": 19.480, "reason": "Błąd"}],
        "heading_degrees": 0, "suggested_hashtags": [], "geoguessr": {}
    }

def _create_csi_zoom_crops(image: Image.Image) -> List[bytes]:
    img_hd = image.copy()
    if img_hd.mode in ("RGBA", "P"): img_hd = img_hd.convert("RGB")
    crops = []
    
    main_img = img_hd.copy()
    if max(main_img.size) > 1600: main_img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    main_img = ImageEnhance.Sharpness(main_img).enhance(1.8)
    try: main_img = ImageOps.autocontrast(main_img, cutoff=1)
    except Exception: pass
    
    buf = BytesIO()
    main_img.save(buf, format="JPEG", quality=85)
    crops.append(buf.getvalue())
    
    w, h = img_hd.size
    if w > 800 and h > 800:
        boxes = [(0, 0, w//2, h//2), (w//2, 0, w, h//2), (0, h//2, w//2, h), (w//2, h//2, w, h)]
        for box in boxes:
            zoom_crop = img_hd.crop(box)
            zoom_crop.thumbnail((1080, 1080), Image.Resampling.LANCZOS)
            zoom_crop = ImageEnhance.Sharpness(zoom_crop).enhance(2.5)
            try: zoom_crop = ImageOps.autocontrast(zoom_crop, cutoff=2)
            except Exception: pass
            buf_zoom = BytesIO()
            zoom_crop.save(buf_zoom, format="JPEG", quality=80)
            crops.append(buf_zoom.getvalue())
            
    return crops

def analyze_images_top3(images: Union[Image.Image, List[Image.Image]], api_key: Optional[str] = None, model_name: str = "gemini-3.6-flash", user_hint: str = "") -> Dict[str, Any]:
    if not isinstance(images, list): images = [images]
    
    gps_data = _extract_gps_from_exif(images[0])
    if gps_data:
        lat = gps_data['lat']
        lon = gps_data['lon']
        geo = reverse_geocode_nominatim(lat, lon)
        return {
            "success": True,
            "used_model": "EXIF-GPS-Bypass (Brak limitów)",
            "deduction_steps": "BEZ LIMITÓW: Aplikacja wykryła oryginalne metadane GPS ze zdjęcia telefonu! Całkowicie pominięto AI, wykorzystano czyste dane satelitarne.",
            "candidates": [
                {
                    "rank": 1, "probability": 100,
                    "exact_street": geo["exact_street"] or "Brak ulicy",
                    "place_name": geo["place_name"] or "Rozpoznane z satelity",
                    "city": geo["city"] or geo.get("region", ""),
                    "region": geo["region"],
                    "country": geo["country"],
                    "latitude": lat, "longitude": lon,
                    "reason": "Oryginalne współrzędne ukryte w pliku zdjęcia (100% pewności)."
                }
            ],
            "heading_degrees": 0, "suggested_hashtags": ["GPS", "NoLimits"], "geoguessr": {}
        }

    raw_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    key = raw_key.strip().strip('"').strip("'")
    if not key: return {"success": False, "error": "Brak klucza API."}

    parts = _create_csi_zoom_crops(images[0])
    hint_text = f"WSKAZÓWKA OD UŻYTKOWNIKA: {user_hint}" if user_hint.strip() else "Brak wskazówki."
    prompt_text = HYPER_PARK_OSINT_PROMPT.replace("{USER_HINT_SECTION}", hint_text)

    models_cascade = ["gemini-3.6-flash"]
    last_error_msg = ""

    for attempt_round in range(2):
        for target_model in models_cascade:
            try:
                if GENAI_SDK_AVAILABLE:
                    client = genai.Client(api_key=key)
                    content_items = [types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in parts]
                    content_items.append(prompt_text)
                    resp = client.models.generate_content(
                        model=target_model,
                        contents=content_items,
                        config=types.GenerateContentConfig(
                            temperature=0.1, max_output_tokens=1500,
                            tools=[types.Tool(google_search=types.GoogleSearch())]
                        )
                    )
                    raw_text = resp.text
                else:
                    content_parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b).decode("utf-8")}} for b in parts]
                    content_parts.append({"text": prompt_text})
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={key}"
                    payload = {
                        "contents": [{"parts": content_parts}],
                        "tools": [{"googleSearch": {}}],
                        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1500}
                    }
                    r = requests.post(url, json=payload, timeout=25)
                    r.raise_for_status()
                    raw_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]

                data = _extract_and_repair_json(raw_text)
                data["candidates"] = data.get("candidates", [])
                
                # NOWA FUNKCJA: WERYFIKACJA W BAZIE MAP (NOMINATIM)
                query = data.get("search_map_query", "")
                if query:
                    map_match = search_map_database(query)
                    if map_match and len(data["candidates"]) > 0:
                        data["candidates"][0]["latitude"] = map_match["lat"]
                        data["candidates"][0]["longitude"] = map_match["lon"]
                        data["candidates"][0]["reason"] = f"📍 SKALIBROWANO Z BAZĄ MAP: Algorytm samodzielnie przeszukał bazę OpenStreetMap dla hasła '{query}' i pobrał satelitarne współrzędne dachu tego obiektu! " + data["candidates"][0].get("reason", "")
                
                while len(data["candidates"]) < 3:
                    base = data["candidates"][0] if data["candidates"] else {"latitude": 52.069, "longitude": 19.480, "city": ""}
                    new_rank = len(data["candidates"]) + 1
                    data["candidates"].append({
                        "rank": new_rank,
                        "probability": 10,
                        "exact_street": f"Alternatywa #{new_rank}",
                        "place_name": "Brak precyzji",
                        "city": base.get("city", ""),
                        "region": "",
                        "country": "Polska",
                        "latitude": float(base.get("latitude", 52.0)) + 0.05,
                        "longitude": float(base.get("longitude", 19.4)) + 0.05,
                        "reason": "Opcja zapasowa"
                    })

                data["success"] = True
                data["used_model"] = target_model
                return data

            except Exception as e:
                err_str = str(e)
                last_error_msg = err_str
                if "429" in err_str: continue
                if "503" in err_str or "404" in err_str: continue
                if "API_KEY_INVALID" in err_str or "400" in err_str: return {"success": False, "error": "Błąd klucza API."}
                break
        time.sleep(1.5)

    return {"success": False, "error": f"API limit 429: {last_error_msg}"}
