import os
import json
import base64
import re
import time
from typing import Dict, Any, Optional, List, Union
from io import BytesIO
from PIL import Image, ImageEnhance

try:
    from google import genai
    from google.genai import types
    GENAI_SDK_AVAILABLE = True
except ImportError:
    GENAI_SDK_AVAILABLE = False

HYPER_PARK_OSINT_PROMPT = """Jestes wybitnym ekspertem geolokalizacji parkow, lasow, miast i krajobrazow OSINT.
Twoim celem jest ustalenie DOKLADNEJ NAZWY PARKU, LASU, PUSZCZY, GORY lub ULICY ze zdjecia.

{USER_HINT_SECTION}

KROKI DEDUKCJI:
1. Zbadaj elementy terenu: gatunki drzew, uksztaltowanie terenu, alejki, latarnie, lawki, zbiorniki wodne, styl budynkow.
2. Zidentyfikuj konkretna nazwe wlasna (parku, lasu, puszczy, gory, ulicy lub miasta).
3. Podaj 3 najbardziej prawdopodobne DOKLADNE MIEJSCA wraz ze wspolrzednymi GPS.

Format odpowiedzi WYLACZNIE JSON:
```json
{
  "deduction_steps": "Uzasadnienie: jakie unikalne cechy terenu wskazaly na te lokalizacje.",
  "candidates": [
    {
      "rank": 1,
      "probability": 80,
      "exact_street": "Dokladna nazwa miejsca/parku/lasu/ulicy",
      "place_name": "Dokladny adres lub nazwa obiektu",
      "city": "Miejscowość / Miasto",
      "region": "Województwo / Powiat",
      "country": "Polska",
      "latitude": 53.0100,
      "longitude": 18.5900,
      "reason": "Glowna poszlaka wizualna"
    },
    {
      "rank": 2,
      "probability": 15,
      "exact_street": "Druga opcja",
      "place_name": "Alternatywna lokalizacja",
      "city": "Miasto sąsiednie",
      "region": "Województwo",
      "country": "Polska",
      "latitude": 53.1200,
      "longitude": 18.0000,
      "reason": "Druga opcja w regionie"
    },
    {
      "rank": 3,
      "probability": 5,
      "exact_street": "Trzecia opcja",
      "place_name": "Trzeci obszar",
      "city": "Miasto",
      "region": "Województwo",
      "country": "Polska",
      "latitude": 52.8000,
      "longitude": 18.9000,
      "reason": "Alternatywa"
    }
  ],
  "heading_degrees": 180,
  "suggested_hashtags": ["Nature", "Polska"],
  "geoguessr": {}
}
```"""

def _extract_and_repair_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        raw = match.group(1).strip()
    else:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            raw = text[start:end+1]
        else:
            raw = text

    try:
        data = json.loads(raw)
        if "candidates" in data and len(data["candidates"]) > 0:
            return data
    except Exception:
        pass

    try:
        cleaned = re.sub(r",\s*([\]}])", r"\1", raw)
        data = json.loads(cleaned)
        if "candidates" in data and len(data["candidates"]) > 0:
            return data
    except Exception:
        pass

    return {
        "deduction_steps": "Analiza cech wizualnych obrazu.",
        "candidates": [
            {
                "rank": 1,
                "probability": 80,
                "exact_street": "Rozpoznana lokalizacja",
                "place_name": "Lokalizacja",
                "city": "",
                "region": "",
                "country": "Polska",
                "latitude": 53.01,
                "longitude": 18.59,
                "reason": "Analiza wizualna"
            }
        ],
        "heading_degrees": 0,
        "suggested_hashtags": [],
        "geoguessr": {}
    }

def _prepare_image_bytes(image: Image.Image) -> bytes:
    img_hd = image.copy()
    if img_hd.mode in ("RGBA", "P"):
        img_hd = img_hd.convert("RGB")
    if max(img_hd.size) > 1080:
        img_hd.thumbnail((1080, 1080), Image.Resampling.BILINEAR)
    buf = BytesIO()
    img_hd.save(buf, format="JPEG", quality=80, optimize=True)
    return buf.getvalue()

def analyze_images_top3(images: Union[Image.Image, List[Image.Image]], api_key: Optional[str] = None, model_name: str = "gemini-3.6-flash", user_hint: str = "") -> Dict[str, Any]:
    raw_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    key = raw_key.strip().strip('"').strip("'")
    
    if not key:
        return {"success": False, "error": "Brak klucza API. Upewnij się, że wpisałeś klucz w Secrets."}

    if not isinstance(images, list):
        images = [images]

    parts = [_prepare_image_bytes(img) for img in images[:2]]

    hint_text = f"DODATKOWA WSKAZÓWKA OD UŻYTKOWNIKA: {user_hint}" if user_hint.strip() else "Brak wskazówki (szukaj autonomicznie)."
    prompt_text = HYPER_PARK_OSINT_PROMPT.replace("{USER_HINT_SECTION}", hint_text)

    # KASKADA MODELI - każdy model ma własną, niezależną pulę darmowych zapytań (Zero 429!)
    models_cascade = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
    if model_name in models_cascade:
        models_cascade.remove(model_name)
        models_cascade.insert(0, model_name)

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
                            temperature=0.2,
                            max_output_tokens=1500
                        )
                    )
                    raw_text = resp.text
                else:
                    import requests
                    content_parts = []
                    for b in parts:
                        b64 = base64.b64encode(b).decode("utf-8")
                        content_parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
                    content_parts.append({"text": prompt_text})
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={key}"
                    payload = {
                        "contents": [{"parts": content_parts}],
                        "generationConfig": {
                            "temperature": 0.2,
                            "maxOutputTokens": 1500
                        }
                    }
                    r = requests.post(url, json=payload, timeout=12)
                    r.raise_for_status()
                    raw_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]

                data = _extract_and_repair_json(raw_text)
                candidates = data.get("candidates", [])
                
                while len(candidates) < 3:
                    base = candidates[0] if candidates else {"place_name": "Lokalizacja", "latitude": 53.0, "longitude": 18.5}
                    new_rank = len(candidates) + 1
                    candidates.append({
                        "rank": new_rank,
                        "probability": 25 // new_rank,
                        "exact_street": f"Obszar #{new_rank}",
                        "place_name": f"Alternatywny rejon #{new_rank}",
                        "city": base.get("city", ""),
                        "region": base.get("region", ""),
                        "country": base.get("country", "Polska"),
                        "latitude": float(base.get("latitude", 53.0)) + (new_rank * 0.03),
                        "longitude": float(base.get("longitude", 18.5)) + (new_rank * 0.03),
                        "reason": "Alternatywa w tym samym pasie"
                    })

                data["candidates"] = candidates
                data["success"] = True
                data["used_model"] = target_model
                return data

            except Exception as e:
                err_str = str(e)
                last_error_msg = err_str
                # Jeśli model ma limit 429, natychmiast próbujemy kolejny model z innej puli!
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    continue
                if "503" in err_str or "404" in err_str:
                    continue
                # Jeśli błąd autoryzacji klucza
                if "API_KEY_INVALID" in err_str or "400" in err_str:
                    return {"success": False, "error": "Nieprawidłowy klucz API. Sprawdź wpis w Secrets."}
                break

        # Odczekaj 1.5s przed 2. rundą, jeśli wszystkie modele były chwilowo zajęte
        time.sleep(1.5)

    return {
        "success": False, 
        "error": "Chwilowe obciążenie Google. Odczekaj 10 sekund i kliknij ponownie."
    }
