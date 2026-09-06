from pathlib import Path
import json
import time

import requests


OUTPUT_DIR = Path(
    r"C:\Users\kavya\JalDrishti\data\cases\ujjani_real"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# Slightly larger area around Ujjani.
SOUTH = 17.95
WEST = 75.00
NORTH = 18.25
EAST = 75.40


OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


HEADERS = {
    "User-Agent": "NeerRaksha-SIH2026/1.0",
    "Accept": "application/json",
}


def run_query(query):
    last_error = None

    for url in OVERPASS_URLS:
        try:
            print()
            print("Querying:", url)

            response = requests.post(
                url,
                data={"data": query},
                headers=HEADERS,
                timeout=180
            )

            if response.status_code != 200:
                print(
                    "HTTP",
                    response.status_code
                )
                print(
                    response.text[:300]
                )
                continue

            data = response.json()

            print(
                "Received",
                len(data.get("elements", [])),
                "OSM elements"
            )

            return data

        except Exception as exc:
            print("Failed:", exc)
            last_error = exc
            time.sleep(2)

    raise RuntimeError(
        f"All Overpass endpoints failed: {last_error}"
    )


def clean_geometry(element):
    geometry = element.get("geometry")

    if not isinstance(geometry, list):
        return []

    coords = []

    for point in geometry:

        # Some Overpass responses may contain null entries.
        if not isinstance(point, dict):
            continue

        lon = point.get("lon")
        lat = point.get("lat")

        if lon is None or lat is None:
            continue

        try:
            lon = float(lon)
            lat = float(lat)
        except (TypeError, ValueError):
            continue

        coords.append([
            lon,
            lat
        ])

    return coords


def save_line_features(
    filename,
    elements,
    property_keys
):
    features = []

    for element in elements:

        if element.get("type") != "way":
            continue

        coords = clean_geometry(
            element
        )

        if len(coords) < 2:
            continue

        tags = element.get(
            "tags",
            {}
        ) or {}

        properties = {
            "osm_id": element.get("id"),
            "osm_type": element.get("type"),
            "source": "OpenStreetMap"
        }

        for key in property_keys:
            properties[key] = tags.get(key)

        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            }
        })

    output = {
        "type": "FeatureCollection",
        "features": features
    }

    path = OUTPUT_DIR / filename

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            indent=2
        )

    print(
        filename,
        ":",
        len(features),
        "features"
    )


def save_point_features(
    filename,
    elements,
    property_keys
):
    features = []

    for element in elements:

        tags = element.get(
            "tags",
            {}
        ) or {}

        lon = element.get("lon")
        lat = element.get("lat")

        if lon is None or lat is None:

            center = element.get(
                "center",
                {}
            ) or {}

            lon = center.get("lon")
            lat = center.get("lat")

        if lon is None or lat is None:
            continue

        try:
            lon = float(lon)
            lat = float(lat)
        except (TypeError, ValueError):
            continue

        properties = {
            "osm_id": element.get("id"),
            "osm_type": element.get("type"),
            "source": "OpenStreetMap"
        }

        for key in property_keys:
            properties[key] = tags.get(key)

        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": {
                "type": "Point",
                "coordinates": [
                    lon,
                    lat
                ]
            }
        })

    output = {
        "type": "FeatureCollection",
        "features": features
    }

    path = OUTPUT_DIR / filename

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            indent=2
        )

    print(
        filename,
        ":",
        len(features),
        "features"
    )


bbox = (
    f"{SOUTH},{WEST},"
    f"{NORTH},{EAST}"
)


# ============================================================
# RIVERS / STREAMS
# ============================================================

river_query = f"""
[out:json][timeout:120];
(
  way["waterway"="river"]({bbox});
  way["waterway"="stream"]({bbox});
  way["waterway"="canal"]({bbox});
);
out tags geom;
"""


river_data = run_query(
    river_query
)

save_line_features(
    "rivers_osm.geojson",
    river_data.get(
        "elements",
        []
    ),
    [
        "name",
        "name:en",
        "waterway"
    ]
)


# ============================================================
# ROADS
# ============================================================

road_query = f"""
[out:json][timeout:120];
way["highway"]({bbox});
out tags geom;
"""


road_data = run_query(
    road_query
)

save_line_features(
    "roads_osm.geojson",
    road_data.get(
        "elements",
        []
    ),
    [
        "name",
        "highway",
        "ref"
    ]
)


# ============================================================
# FACILITIES
# ============================================================

facility_query = f"""
[out:json][timeout:120];
(
  node["amenity"~"hospital|clinic|school|college|police|fire_station"]({bbox});
  way["amenity"~"hospital|clinic|school|college|police|fire_station"]({bbox});
);
out tags center;
"""


facility_data = run_query(
    facility_query
)

save_point_features(
    "facilities_osm.geojson",
    facility_data.get(
        "elements",
        []
    ),
    [
        "name",
        "amenity"
    ]
)


# ============================================================
# SETTLEMENTS
# ============================================================

settlement_query = f"""
[out:json][timeout:120];
(
  node["place"~"city|town|village|hamlet"]({bbox});
);
out tags;
"""


settlement_data = run_query(
    settlement_query
)

save_point_features(
    "settlements_osm.geojson",
    settlement_data.get(
        "elements",
        []
    ),
    [
        "name",
        "place"
    ]
)


print()
print("==============================")
print("DONE")
print("==============================")
print("Output folder:")
print(OUTPUT_DIR)