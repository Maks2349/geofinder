import urllib.parse
from typing import Dict, List, Any, Optional

def clean_hashtag(tag: str) -> str:
    return tag.replace("#", "").replace(" ", "").strip()

def get_social_links(place_name: str, country: str, city: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None, hashtags: Optional[List[str]] = None, heading: int = 0) -> Dict[str, Any]:
    query_parts = [place_name]
    if city and city not in place_name:
        query_parts.append(city)
    if country and country not in place_name:
        query_parts.append(country)
    
    full_query = " ".join(query_parts)
    encoded_query = urllib.parse.quote(full_query)

    cleaned_tags = []
    if hashtags:
        for h in hashtags:
            c = clean_hashtag(h)
            if c and c not in cleaned_tags:
                cleaned_tags.append(c)
    
    base_tag = clean_hashtag(place_name)
    if base_tag and base_tag not in cleaned_tags:
        cleaned_tags.insert(0, base_tag)
    if city:
        city_tag = clean_hashtag(city)
        if city_tag not in cleaned_tags:
            cleaned_tags.append(city_tag)

    tiktok_tag_links = []
    for tag in cleaned_tags[:4]:
        tiktok_tag_links.append({
            "name": f"#{tag}",
            "url": f"https://www.tiktok.com/tag/{urllib.parse.quote(tag)}"
        })

    maps_link = None
    streetview_link = None
    earth_3d_link = None
    webcams_link = None

    if lat is not None and lon is not None:
        maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        streetview_link = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}&heading={heading}&pitch=0&fov=85"
        earth_3d_link = f"https://earth.google.com/web/@{lat},{lon},150a,800d,35y,{heading}h,60t,0r"
        webcams_link = f"https://www.windy.com/-Webcams/webcams?{lat},{lon},11"
    else:
        maps_link = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
        webcams_link = f"https://www.windy.com/-Webcams/webcams?52.2297,21.0122,5"

    return {
        "tiktok": {
            "search_url": f"https://www.tiktok.com/search?q={encoded_query}",
            "tags": tiktok_tag_links
        },
        "instagram": {
            "search_url": f"https://www.instagram.com/explore/search/keyword/?q={encoded_query}",
        },
        "maps": {
            "google_maps": maps_link,
            "street_view": streetview_link,
            "earth_3d": earth_3d_link,
            "webcams_live": webcams_link
        },
        "reverse_image": {
            "google_lens": "https://lens.google.com/",
            "yandex": "https://yandex.com/images/search?rpt=imageview"
        }
    }
