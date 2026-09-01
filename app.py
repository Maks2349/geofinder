import streamlit as st
import json
import os
from PIL import Image
from streamlit_folium import st_folium

from modules.exif_reader import extract_exif_data
from modules.ai_geolocator import analyze_images_top3
from modules.social_search import get_social_links
from modules.map_renderer import create_multi_location_map

st.set_page_config(
    page_title="GeoFinder 🌍",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #3B82F6, #8B5CF6, #EC4899);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.1rem;
    }
    .sub-title {
        color: #64748B;
        font-size: 1rem;
        margin-bottom: 1rem;
    }
    .candidate-card-1 {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border: 2px solid #EF4444;
        border-radius: 12px;
        padding: 16px 20px;
        color: white;
        margin-bottom: 10px;
        box-shadow: 0 4px 15px rgba(239, 68, 68, 0.25);
    }
    .candidate-card-2 {
        background: #1E293B;
        border: 2px solid #3B82F6;
        border-radius: 10px;
        padding: 14px 18px;
        color: white;
        margin-bottom: 8px;
    }
    .candidate-card-3 {
        background: #1E293B;
        border: 2px solid #A855F7;
        border-radius: 10px;
        padding: 14px 18px;
        color: white;
        margin-bottom: 8px;
    }
    .prob-badge-1 {
        background-color: #DC2626;
        color: white;
        padding: 4px 10px;
        border-radius: 14px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .prob-badge-2 {
        background-color: #2563EB;
        color: white;
        padding: 4px 10px;
        border-radius: 14px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .prob-badge-3 {
        background-color: #9333EA;
        color: white;
        padding: 4px 10px;
        border-radius: 14px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .social-btn {
        display: inline-block;
        padding: 9px 15px;
        border-radius: 8px;
        font-weight: bold;
        text-decoration: none;
        margin-right: 8px;
        margin-bottom: 8px;
        font-size: 0.92rem;
    }
    .sniper-btn {
        background: linear-gradient(90deg, #EF4444, #F97316);
        color: #FFFFFF !important;
    }
    .earth-btn {
        background-color: #059669;
        color: #FFFFFF !important;
    }
    .webcam-btn {
        background-color: #0284C7;
        color: #FFFFFF !important;
    }
    .tiktok-btn {
        background-color: #000000;
        color: #FFFFFF !important;
        border: 1px solid #444;
    }
    .insta-btn {
        background: linear-gradient(45deg, #f09433 0%, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%);
        color: #FFFFFF !important;
    }
    .maps-btn {
        background-color: #2563EB;
        color: #FFFFFF !important;
    }
    .paste-hint {
        background-color: #F1F5F9;
        border: 1px dashed #94A3B8;
        padding: 8px 14px;
        border-radius: 8px;
        color: #475569;
        font-size: 0.88rem;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

if "geo_result" not in st.session_state:
    st.session_state["geo_result"] = None
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "map_key" not in st.session_state:
    st.session_state["map_key"] = 0

loaded_secret_key = ""
try:
    if "GEMINI_API_KEY" in st.secrets:
        loaded_secret_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass

if not loaded_secret_key:
    loaded_secret_key = os.environ.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/globe.png", width=65)
    st.header("⚙️ Ustawienia")
    
    if loaded_secret_key:
        st.success("✅ Klucz API wczytany automatycznie!")
        api_key_input = loaded_secret_key
    else:
        api_key_input = st.text_input(
            "Klucz Google Gemini API",
            type="password",
            value="",
            help="Pobierz bezpłatny klucz na https://aistudio.google.com/app/apikey"
        )
    
    st.divider()
    model_choice = st.selectbox(
        "Silnik AI",
        ["gemini-3.6-flash (Zalecany)", "gemini-3.7-flash (Pro Reasoning)"],
        index=0
    )
    selected_model = model_choice.split(" ")[0]

col_title, col_reset = st.columns([3.5, 1.2])
with col_title:
    st.markdown('<div class="main-title">GeoFinder 🌍</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Precyzyjne namierzanie dokładnej ulicy i budynku na mapie Google</div>', unsafe_allow_html=True)

with col_reset:
    if st.button("🔄 Wyszukaj ponownie (Wyczyść)", use_container_width=True):
        st.session_state["geo_result"] = None
        st.session_state["uploader_key"] += 1
        st.session_state["map_key"] += 1
        st.rerun()

st.markdown('<div class="paste-hint">📸 <b>Wgraj lub wklej (Ctrl + V):</b> Przeciągnij zdjęcie lub wklej ze schowka.</div>', unsafe_allow_html=True)

uploaded_files = st.file_uploader(
    "Wybierz plik ze zdjęciem / zrzutem ekranu",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    key=f"file_uploader_{st.session_state['uploader_key']}"
)

loaded_images = []
if uploaded_files:
    for f in uploaded_files:
        try:
            loaded_images.append(Image.open(f))
        except Exception:
            pass

if loaded_images:
    col_imgs, col_controls = st.columns([1.2, 1])
    
    with col_imgs:
        cols_grid = st.columns(min(len(loaded_images), 3))
        for i, img in enumerate(loaded_images[:3]):
            with cols_grid[i]:
                st.image(img, caption=f"Kadr #{i+1}", use_container_width=True)

        has_gps = False
        first_exif = extract_exif_data(loaded_images[0])
        if first_exif.get("has_gps"):
            has_gps = True
            st.success(f"📍 Wykryto GPS w pliku! ({first_exif['latitude']}, {first_exif['longitude']})")

    with col_controls:
        st.markdown("### 🎯 Namierzanie dokładnej ulicy")
        st.write("Silnik przeanalizuje tablice, styl zabudowy, numery, infrastrukturę i wbije pinezkę w konkretną ulicę na mapie.")
        
        btn_search = st.button("🎯 Namierz dokładną ulicę i adres!", type="primary", use_container_width=True)

    if btn_search:
        if has_gps:
            flat = first_exif["latitude"]
            flon = first_exif["longitude"]
            place = "Lokalizacja z aparatu"
            slinks = get_social_links(place, "", "", flat, flon)
            st.session_state["map_key"] += 1
            st.session_state["geo_result"] = {
                "candidates": [{
                    "rank": 1,
                    "probability": 100,
                    "exact_street": "Współrzędne z pliku",
                    "place_name": place,
                    "city": "",
                    "region": "GPS",
                    "country": "Polska",
                    "latitude": flat,
                    "longitude": flon,
                    "reason": "Odczytano bezpośrednio z metadanych aparatu"
                }],
                "has_gps": True,
                "social_links": slinks,
                "heading": 0,
                "deduction": "Odczytano oryginalne dane GPS z aparatu.",
                "geoguessr": {}
            }
        else:
            if not api_key_input:
                st.warning("⚠️ Wprowadź klucz Gemini API w pasku po lewej stronie.")
            else:
                with st.spinner("🕵️‍♂️ Analiza ulic, tablic i infrastruktury w bazach danych..."):
                    ai_res = analyze_images_top3(
                        images=loaded_images,
                        api_key=api_key_input,
                        model_name=selected_model
                    )

                if not ai_res.get("success", False):
                    st.error(f"Problem: {ai_res.get('error', 'Nieznany błąd')}")
                else:
                    candidates = ai_res.get("candidates", [])
                    top1 = candidates[0] if candidates else {}
                    flat = float(top1.get("latitude", 52.0))
                    flon = float(top1.get("longitude", 19.0))
                    pname = top1.get("place_name", "Rozpoznane miejsce")
                    city = top1.get("city", "")
                    country = top1.get("country", "")
                    heading = int(ai_res.get("heading_degrees", 0))

                    slinks = get_social_links(
                        place_name=pname,
                        country=country,
                        city=city,
                        lat=flat,
                        lon=flon,
                        hashtags=ai_res.get("suggested_hashtags", []),
                        heading=heading
                    )

                    st.session_state["map_key"] += 1
                    st.session_state["geo_result"] = {
                        "candidates": candidates,
                        "has_gps": False,
                        "social_links": slinks,
                        "heading": heading,
                        "deduction": ai_res.get("deduction_steps", ""),
                        "geoguessr": ai_res.get("geoguessr", {})
                    }

# WYŚWIETLANIE WYNIKÓW
res = st.session_state.get("geo_result")
if res is not None:
    st.divider()
    candidates = res.get("candidates", [])
    
    st.subheader("🏠 Wytypowane Dokładne Ulice i Adresy:")

    col_c1, col_c2, col_c3 = st.columns(3)
    
    if len(candidates) >= 1:
        c1 = candidates[0]
        with col_c1:
            st.markdown(f"""
            <div class="candidate-card-1">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:bold; font-size:1.05rem; color:#FCA5A5;">🔴 #1 Główna Ulica</span>
                    <span class="prob-badge-1">{c1.get('probability', 80)}%</span>
                </div>
                <h2 style="margin:0 0 4px 0; color:white; font-size:1.4rem;">{c1.get('exact_street', c1.get('place_name'))}</h2>
                <div style="font-size:0.95rem; color:#E2E8F0; margin-bottom:6px;">📍 {c1.get('place_name')}</div>
                <div style="font-size:0.85rem; color:#94A3B8; margin-bottom:6px;">{c1.get('city') + ', ' if c1.get('city') else ''}{c1.get('region') + ', ' if c1.get('region') else ''}{c1.get('country')}</div>
                <div style="font-size:0.85rem; color:#34D399;"><b>Współrzędne:</b> {c1.get('latitude', 0.0):.5f}, {c1.get('longitude', 0.0):.5f}</div>
                {f'<div style="font-size:0.8rem; color:#CBD5E1; margin-top:6px;"><i>{c1.get("reason")}</i></div>' if c1.get("reason") else ''}
            </div>
            """, unsafe_allow_html=True)

    if len(candidates) >= 2:
        c2 = candidates[1]
        with col_c2:
            st.markdown(f"""
            <div class="candidate-card-2">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:bold; font-size:1.05rem; color:#93C5FD;">🔵 #2 Alternatywna Ulica</span>
                    <span class="prob-badge-2">{c2.get('probability', 15)}%</span>
                </div>
                <h3 style="margin:0 0 4px 0; color:white; font-size:1.2rem;">{c2.get('exact_street', c2.get('place_name'))}</h3>
                <div style="font-size:0.9rem; color:#CBD5E1; margin-bottom:6px;">📍 {c2.get('place_name')}</div>
                <div style="font-size:0.85rem; color:#94A3B8; margin-bottom:6px;">{c2.get('city') + ', ' if c2.get('city') else ''}{c2.get('region') + ', ' if c2.get('region') else ''}{c2.get('country')}</div>
                {f'<div style="font-size:0.8rem; color:#94A3B8; margin-top:6px;"><i>{c2.get("reason")}</i></div>' if c2.get("reason") else ''}
            </div>
            """, unsafe_allow_html=True)

    if len(candidates) >= 3:
        c3 = candidates[2]
        with col_c3:
            st.markdown(f"""
            <div class="candidate-card-3">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:bold; font-size:1.05rem; color:#D8B4FE;">🟣 #3 Alternatywna Ulica</span>
                    <span class="prob-badge-3">{c3.get('probability', 5)}%</span>
                </div>
                <h3 style="margin:0 0 4px 0; color:white; font-size:1.2rem;">{c3.get('exact_street', c3.get('place_name'))}</h3>
                <div style="font-size:0.9rem; color:#CBD5E1; margin-bottom:6px;">📍 {c3.get('place_name')}</div>
                <div style="font-size:0.85rem; color:#94A3B8; margin-bottom:6px;">{c3.get('city') + ', ' if c3.get('city') else ''}{c3.get('region') + ', ' if c3.get('region') else ''}{c3.get('country')}</div>
                {f'<div style="font-size:0.8rem; color:#94A3B8; margin-top:6px;"><i>{c3.get("reason")}</i></div>' if c3.get("reason") else ''}
            </div>
            """, unsafe_allow_html=True)

    tab_map, tab_deduction, tab_sniper, tab_social = st.tabs([
        "🗺️ Mapa Google (Pinezki w Ulicach)",
        "🕵️‍♂️ Śledcza Dedukcja OSINT",
        "🎯 Snajper 3D (Widok 360° POV)",
        "📱 TikTok, Kamery LIVE & Social"
    ])

    with tab_map:
        st.write("🔴 **Czerwona pinezka:** Główna wytypowana ulica | 🔵 **Niebieska:** Alternatywa A | 🟣 **Fioletowa:** Alternatywa B")
        multi_map = create_multi_location_map(candidates, is_gps=res["has_gps"])
        st_folium(multi_map, key=f"folium_map_view_{st.session_state['map_key']}", width=None, height=480, returned_objects=[])

    with tab_deduction:
        st.subheader("🕵️‍♂️ Raport dedukcji: Jak ustalono tę ulicę?")
        st.write(res.get("deduction", "Analiza cech obrazu."))

    with tab_sniper:
        st.subheader("🎯 Snajper 3D: Zanurzenie w perspektywę 360° w tę ulicę")
        sl = res["social_links"]
        street_url = sl["maps"]["street_view"]
        earth_url = sl["maps"]["earth_3d"]

        st.markdown(f"""
        <div style="margin-bottom: 15px;">
            <a class="social-btn sniper-btn" href="{street_url}" target="_blank">🎯 Otwórz Street View 360° tej ulicy &rarr;</a>
            <a class="social-btn earth-btn" href="{earth_url}" target="_blank">🌐 Otwórz Google Earth 3D &rarr;</a>
        </div>
        """, unsafe_allow_html=True)

    with tab_social:
        st.subheader("📱 TikTok, Kamery LIVE & Wyszukiwanie Obrazem")
        sl = res["social_links"]
        tiktok_url = sl["tiktok"]["search_url"]
        gmaps_url = sl["maps"]["google_maps"]
        lens_url = sl["reverse_image"]["google_lens"]

        st.markdown(f"""
        <div>
            <a class="social-btn sniper-btn" href="{lens_url}" target="_blank">🔍 Google Lens (Wyszukaj to samo zdjęcie w sieci) &rarr;</a>
            <a class="social-btn tiktok-btn" href="{tiktok_url}" target="_blank">🎵 Szukaj na TikToku &rarr;</a>
            <a class="social-btn maps-btn" href="{gmaps_url}" target="_blank">🗺️ Otwórz w Google Maps &rarr;</a>
        </div>
        """, unsafe_allow_html=True)
