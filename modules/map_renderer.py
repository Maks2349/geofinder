import folium
from typing import Optional, Dict, Any, List

def create_multi_location_map(
    candidates: List[Dict[str, Any]],
    is_gps: bool = False
) -> folium.Map:
    """
    Tworzy mape Google z dokladnymi pinezkami wbijajacymi sie w ulice (bez sztucznego promienia 5km).
    """
    if not candidates:
        return folium.Map(location=[52.2, 19.4], zoom_start=6)

    valid_candidates = []
    seen_coords = set()

    for idx, c in enumerate(candidates[:3]):
        lat = c.get("latitude")
        lon = c.get("longitude")
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            continue
        
        coord_key = (round(lat, 4), round(lon, 4))
        if coord_key in seen_coords:
            lat += (idx * 0.005)
            lon += (idx * 0.005)
        seen_coords.add((round(lat, 4), round(lon, 4)))

        c_copy = dict(c)
        c_copy["latitude"] = lat
        c_copy["longitude"] = lon
        valid_candidates.append(c_copy)

    if not valid_candidates:
        return folium.Map(location=[52.2, 19.4], zoom_start=6)

    top1 = valid_candidates[0]
    
    m = folium.Map(
        location=[top1["latitude"], top1["longitude"]],
        zoom_start=14,
        tiles=None,
        control_scale=True
    )

    # 1. Google Maps (Czytelne ulice, numery i miasta)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
        attr="Google Maps",
        name="🗺️ Ulice & Miasta (Google Maps)",
        control=True
    ).add_to(m)

    # 2. Google Maps Hybrydowa (Satelita + ulice)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Maps Satellite",
        name="🛰️ Satelita + Ulice (Google)",
        control=True
    ).add_to(m)

    # 3. OpenStreetMap
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="🌐 OpenStreetMap",
        control=True
    ).add_to(m)

    colors = ["red" if not is_gps else "green", "blue", "purple"]
    labels = ["🥇 Wybór #1 (Główna Ulica)", "🥈 Alternatywa A", "🥉 Alternatywa B"]
    
    bounds_points = []

    for idx, c in enumerate(valid_candidates):
        clat = c["latitude"]
        clon = c["longitude"]
        bounds_points.append([clat, clon])
        
        rank = idx + 1
        st_name = c.get("exact_street") or c.get("place_name", f"Ulica #{rank}")
        full_addr = c.get("place_name", st_name)
        prob = c.get("probability", 80 if rank == 1 else 10)
        reason = c.get("reason", "")
        color = colors[idx] if idx < len(colors) else "gray"

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 230px; padding: 6px;">
            <div style="font-size: 13px; font-weight: bold; color: #0F172A; margin-bottom: 4px;">
                {labels[idx] if idx < len(labels) else f'#{rank}'}
            </div>
            <div style="font-size: 13px; color: #DC2626; font-weight: bold; margin-bottom: 4px;">
                📍 {st_name}
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 6px;">
                <b>Adres:</b> {full_addr}<br/>
                <b>Pewność:</b> <span style="color: #2563EB; font-weight: bold;">{prob}%</span><br/>
                <b>Współrzędne:</b> <code>{clat:.5f}, {clon:.5f}</code>
            </div>
            {f'<div style="font-size: 10px; color: #334155; background: #F8FAFC; border: 1px solid #E2E8F0; padding: 5px; border-radius: 4px; margin-bottom: 6px;">{reason}</div>' if reason else ''}
            <a href="https://www.google.com/maps/search/?api=1&query={clat},{clon}" target="_blank" 
               style="display: inline-block; background-color: #2563EB; color: white; padding: 5px 10px; text-decoration: none; border-radius: 5px; font-size: 11px; font-weight: bold;">
               Zobacz ten budynek w Google Maps &rarr;
            </a>
        </div>
        """

        folium.Marker(
            location=[clat, clon],
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=f"📍 {st_name} ({prob}%)",
            icon=folium.Icon(color=color, icon="home" if idx == 0 else "map-marker", prefix="fa")
        ).add_to(m)

    if len(bounds_points) > 1:
        m.fit_bounds(bounds_points, padding=(50, 50))

    folium.LayerControl(position="topright", collapsed=False).add_to(m)
    return m
