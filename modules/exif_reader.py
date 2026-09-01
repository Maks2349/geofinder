from typing import Optional, Dict, Any
from PIL import Image, ExifTags

def _convert_to_degrees(value) -> float:
    """Konwertuje wspolrzedne GPS w formacie stopni, minut, sekund (DMS) na stopnie dziesietne (DD)."""
    try:
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return 0.0

def extract_exif_data(image: Image.Image) -> Dict[str, Any]:
    """
    Odczytuje metadane EXIF oraz koordynaty GPS ze zdjecia.
    """
    result = {
        "has_gps": False,
        "latitude": None,
        "longitude": None,
        "altitude": None,
        "timestamp": None,
        "camera_make": None,
        "camera_model": None,
        "software": None,
        "raw_tags": {}
    }

    try:
        exif = image.getexif()
        if not exif:
            return result

        for tag_id, val in exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            if tag_name == "Make":
                result["camera_make"] = str(val).strip()
            elif tag_name == "Model":
                result["camera_model"] = str(val).strip()
            elif tag_name == "Software":
                result["software"] = str(val).strip()
            elif tag_name == "DateTime":
                result["timestamp"] = str(val).strip()

        # Pobieranie IFD z GPS (tag 0x8825 = 34853)
        gps_ifd = exif.get_ifd(0x8825)
        if gps_ifd:
            gps_tags = {}
            for t_id, val in gps_ifd.items():
                t_name = ExifTags.GPSTAGS.get(t_id, str(t_id))
                gps_tags[t_name] = val

            lat_val = gps_tags.get("GPSLatitude")
            lat_ref = gps_tags.get("GPSLatitudeRef", "N")
            lon_val = gps_tags.get("GPSLongitude")
            lon_ref = gps_tags.get("GPSLongitudeRef", "E")
            alt_val = gps_tags.get("GPSAltitude")

            if lat_val and lon_val:
                lat = _convert_to_degrees(lat_val)
                if lat_ref != "N":
                    lat = -lat

                lon = _convert_to_degrees(lon_val)
                if lon_ref != "E":
                    lon = -lon

                if lat != 0.0 or lon != 0.0:
                    result["has_gps"] = True
                    result["latitude"] = round(lat, 6)
                    result["longitude"] = round(lon, 6)

            if alt_val:
                try:
                    result["altitude"] = round(float(alt_val), 1)
                except Exception:
                    pass

    except Exception as e:
        result["error"] = str(e)

    return result
