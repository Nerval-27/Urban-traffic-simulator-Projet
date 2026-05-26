"""Nettoie les donnees OpenStreetMap brutes pour produire la carte utilisee par la simulation."""
import json
import sys
import math
import os
from simulation.utils import haversine


# Lecture du fichier OSM.

if len(sys.argv) < 2:
    exit()

# Fichier brut exporte depuis OpenStreetMap / Overpass.
osm_file = sys.argv[1]

with open(osm_file, "r") as f:
    osm = json.load(f)

# Liste brute des objets OSM : nodes, ways, feux, passages pietons.
elements = osm["elements"]

# Index temporaire des noeuds GPS par identifiant OSM.
nodes = {}
# Routes OSM conservees avant transformation en format projet.
ways = []

# Types de routes gardes pour la circulation automobile.
CARROSSABLE = [
    "motorway", "trunk", "primary", "secondary",
    "tertiary", "residential", "unclassified", "service"
]


# Extraction des nodes et ways.

for el in elements:
    if el["type"] == "node":
        nid = el["id"]
        # Certains exports contiennent le même node plusieurs fois.
        if nid not in nodes or "tags" in el:
            nodes[nid] = {
                "lat": el["lat"],
                "lon": el["lon"],
                "tags": el.get("tags", {})
            }

    elif el["type"] == "way":
        highway = el.get("tags", {}).get("highway")
        if highway in CARROSSABLE:
            ways.append(el)



# Détection des intersections.

usage = {}
for way in ways:
    for nid in way["nodes"]:
        usage[nid] = usage.get(nid, 0) + 1

intersections = {nid for nid, count in usage.items() if count >= 2}



# Construction des routes.


def compute_length(node_list):
    """Additionne les distances entre les noeuds d une route OSM."""
    total = 0
    for i in range(len(node_list) - 1):
        n1 = nodes[node_list[i]]
        n2 = nodes[node_list[i+1]]
        total += haversine(n1["lat"], n1["lon"], n2["lat"], n2["lon"])
    return total

# Vitesses par defaut par type de route, en metres par seconde.
VITESSES = {
    "motorway": 33.3, 
    "trunk": 27.7,
    "primary": 22.2,
    "secondary": 16.6,
    "tertiary": 13.8,
    "residential": 11.1,
    "unclassified": 11.1,
    "service": 8.3
}

# Routes nettoyees qui seront ecrites dans map_clean.json.
roads = []
for way in ways:
    way_id = way["id"]
    nlist = list(way["nodes"])
    highway = way["tags"]["highway"]
    oneway_tag = str(way["tags"].get("oneway", "")).strip().lower()
    junction_tag = str(way["tags"].get("junction", "")).strip().lower()
    is_oneway = (
        oneway_tag in ("yes", "true", "1")
        or junction_tag in ("roundabout", "circular")
        or highway == "motorway"
    )
    if oneway_tag == "-1":
        nlist.reverse()
        is_oneway = True

    length = compute_length(nlist)

    next_inter = None
    for nid in nlist[::-1]:
        if nid in intersections:
            next_inter = nid
            break

    roads.append({
        "id": way_id,
        "name": way["tags"].get("name", "Inconnue"),
        "length": length,
        "speed_limit": VITESSES.get(highway, 11.1),
        "oneway": is_oneway,
        "nodes": nlist,
        "next": next_inter
    })



# Construction des intersections.


# Liste finale des carrefours detectes.
intersections_list = []

# Index des carrefours, pratique pour remplir ensuite incoming/outgoing.
inter_dict = {
    nid: {
        "id": nid,
        "incoming": [],
        "outgoing": [],
        "has_light": (nodes[nid].get("tags", {}).get("highway") == "traffic_signals"),
        "lat": nodes[nid]["lat"],
        "lon": nodes[nid]["lon"]
    }
    for nid in intersections
}

for road in roads:
    r_id = road["id"]
    nlist = road["nodes"]

    start = None
    end = None

    for nid in nlist:
        if nid in intersections:
            start = nid
            break

    for nid in reversed(nlist):
        if nid in intersections:
            end = nid
            break

    if start is not None and end is not None and start != end:
        inter_dict[start]["outgoing"].append(r_id)
        inter_dict[end]["incoming"].append(r_id)

intersections_list = list(inter_dict.values())


# Extraction des feux et passages piétons.

# Feux de circulation gardes dans la carte nettoyee.
signals_list = []
# Passages pietons gardes dans la carte nettoyee.
crossings_list = []

for nid, ninfo in nodes.items():
    tags = ninfo.get("tags", {})
    if tags.get("highway") == "traffic_signals":
        signals_list.append({
            "id": nid,
            "lat": ninfo["lat"],
            "lon": ninfo["lon"]
        })
    elif tags.get("highway") == "crossing":
        crossings_list.append({
            "id": nid,
            "lat": ninfo["lat"],
            "lon": ninfo["lon"],
            "is_regulated": tags.get("crossing") == "traffic_signals"
        })



# Export de la carte nettoyée.
# Coordonnees GPS de tous les noeuds, avec des cles texte pour le JSON.
nodes_coords = {str(nid): {"lat": ninfo["lat"], "lon": ninfo["lon"]} for nid, ninfo in nodes.items()}

# Objet final attendu par le loader de la simulation.
output = {
    "roads": roads,
    "intersections": intersections_list,
    "feux": signals_list,
    "passages": crossings_list,
    "nodes": nodes_coords
}

# Fichier nettoye lu ensuite par make run, make rl-train et make rl-bench.
file_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "map_clean.json")
with open(file_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"{file_path} généré !")
print(f"{len(roads)} routes")
print(f"{len(intersections_list)} intersections")
print(f"{len(signals_list)} feux de circulation")
print(f"{len(crossings_list)} passages piétons")
