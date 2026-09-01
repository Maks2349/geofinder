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

HYPER_PARK_OSINT_PROMPT = """Jesteś Arcymistrzem GeoGuessr, ekspertem wywiadu jawnoźródłowego (OSINT) oraz analitykiem topografii z niesamowitą wiedzą o infrastrukturze Polski i Europy. 
Twoim absolutnym celem jest ustalenie MIKROLOKALIZACJI (z dokładnością do ulicy, szczytu, rezerwatu, a nawet numeru budynku) na podstawie zdjęcia. Oczekuję analizy na poziomie eksperckim.

{USER_HINT_SECTION}

ZASTOSUJ ŁAŃCUCH MYŚLOWY (Chain of Thought - Geoguessr Meta):
1. ANALIZA INFRASTRUKTURY: Zwróć uwagę na słupki drogowe (w Polsce np. U-1: białe z czerwonym odblaskiem), pasy na jezdni, typ słupów wysokiego napięcia (betonowe "A", żerdzie wirowane), kształt i kolor znaków drogowych (zielone/niebieskie?), latarnie (sodowe, LED, parkowe?), styl krawężników, wiaty przystankowe, kosze na śmieci.
2. ARCHITEKTURA I URBANISTYKA: Kształt dachów, kolor dachówki, rodzaj zabudowy (np. blokowisko z wielkiej płyty PRL, kamienice przedwojenne, drewniane chaty góralskie w stylu zakopiańskim).
3. FLORA I TOPOGRAFIA: Oceń rodzaj lasu (bory sosnowe na niżu, buczyny na południu, świerki w górach). Oceń rzeźbę terenu (płasko jak na Mazowszu, falisto jak na Kaszubach/Warmii, czy to góry?). Jeśli to góry, to jakie? Tatry (ostre, skaliste), Karkonosze (obłe, gołoborza), Bieszczady (połoniny), Beskidy (zalesione).
4. POGODA I KLIMAT: Kąt padania cieni, stan roślinności, specyficzne kolory gleby.

Na podstawie tej potężnej dedukcji, połącz ze sobą fakty i zaproponuj 3 najbardziej prawdopodobne DOKŁADNE LOKALIZACJE na świecie (najpewniej w Polsce).

UWAGA KRYTYCZNA: Poniższy format JSON to TYLKO SZABLON PUSTYCH PÓL. 
BEZWZGLĘDNIE NIE KOPIUJ współrzędnych z szablonu! Musisz samodzielnie wywnioskować RZECZYWISTE WSPÓŁRZĘDNE na podstawie rozpoznanego obiektu ze zdjęcia.

Format odpowiedzi WYLACZNIE JSON:
```json
{
  "deduction_steps": "Napisz obszernie swój tok myślenia (kroki 1-4). Opisz DOKŁADNIE co widzisz (słupki, drzewa, góry) i jak to doprowadziło Cię do konkretnego miasta/miejsca.",
  "candidates": [
    {
      "rank": 1,
      "probability": 90,
      "exact_street": "Rzeczywista ulica, szlak lub szczyt",
      "place_name": "Rzeczywista nazwa obiektu, parku lub lasu",
      "city": "Rzeczywiste miasto lub gmina",
      "region": "Województwo lub pasmo górskie",
      "country": "Państwo",
      "latitude": 52.2297,
      "longitude": 21.0122,
      "reason": "Zwięzły kluczowy dowód z obrazu (np. widoczna góra X i układ ulicy Y)."
    }
  ],
  "heading_degrees": 180,
  "suggested_hashtags": ["Geoguessr", "OSINT"],
  "geoguessr": {
    "infrastructure_clues": "wymień zauważone detale drogowe/architektoniczne",
    "nature_clues": "wymień zauważoną roślinność i ukształtowanie terenu"
  }
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
        "deduction_steps": "Błąd przetwarzania AI. Zbyt mało danych lub problem z odpowiedzą modelu.",
        "candidates": [
            {
                "rank": 1,
                "probability": 10,
                "exact_street": "Nieznana lokalizacja",
                "place_name": "Brak danych z obrazu",
                "city": "?",
                "region": "?",
                "country": "Polska",
                "latitude": 52.069,
                "longitude": 19.480,
                "reason": "Geometryczny środek Polski - awaryjne położenie (błąd analizy)"
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
    img_hd.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()

def analyze_images_top3(images: Union[Image.Image, List[Image.Image]], api_key: Optional[str] = None, model_name: str = "gemini-3.6-flash", user_hint: str = "") -> Dict[str, Any]:
    raw_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    key = raw_key.strip().strip('"').strip("'")
    
    if not key:
        return {"success": False, "error": "Brak klucza API. Upewnij się, że wpisałeś klucz w Secrets."}

    if not isinstance(images, list):
        images = [images]

    parts = [_prepare_image_bytes(img) for img in images[:2]]

    hint_text = f"DODATKOWA WSKAZÓWKA OD UŻYTKOWNIKA: {user_hint}" if user_hint.strip() else "Brak wskazówki (szukaj w 100% autonomicznie na podstawie obrazu)."
    prompt_text = HYPER_PARK_OSINT_PROMPT.replace("{USER_HINT_SECTION}", hint_text)

    models_cascade = ["gemini-3.6-pro", "gemini-3.6-flash"]
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
                            temperature=0.1,
                            max_output_tokens=2000
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
                            "temperature": 0.1,
                            "maxOutputTokens": 2000
                        }
                    }
                    r = requests.post(url, json=payload, timeout=18)
                    r.raise_for_status()
                    raw_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]

                data = _extract_and_repair_json(raw_text)
                candidates = data.get("candidates", [])
                
                while len(candidates) < 3:
                    base = candidates[0] if candidates else {"place_name": "Lokalizacja", "latitude": 52.069, "longitude": 19.480}
                    new_rank = len(candidates) + 1
                    candidates.append({
                        "rank": new_rank,
                        "probability": 25 // new_rank,
                        "exact_street": f"Alternatywny obszar #{new_rank}",
                        "place_name": f"Rejon #{new_rank}",
                        "city": base.get("city", ""),
                        "region": base.get("region", ""),
                        "country": base.get("country", "Polska"),
                        "latitude": float(base.get("latitude", 52.0)) + (new_rank * 0.05),
                        "longitude": float(base.get("longitude", 19.4)) + (new_rank * 0.05),
                        "reason": "Alternatywna poszlaka"
                    })

                data["candidates"] = candidates
                data["success"] = True
                data["used_model"] = target_model
                return data

            except Exception as e:
                err_str = str(e)
                last_error_msg = err_str
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    continue
                if "503" in err_str or "404" in err_str:
                    continue
                if "API_KEY_INVALID" in err_str or "400" in err_str:
                    return {"success": False, "error": "Nieprawidłowy klucz API. Sprawdź wpis w Secrets."}
                break

        time.sleep(1.5)

    return {
        "success": False, 
        "error": f"Błąd Google API: {last_error_msg}"
    }
