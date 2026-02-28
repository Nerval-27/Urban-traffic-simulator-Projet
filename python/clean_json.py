import json
import sys
import math
import os
from utils import haversine


# LECTURE DU FICHIER OSM

if len(sys.argv) < 2:
    exit()

osm_file = sys.argv[1]

with open(osm_file, "r") as f:
    osm = json.load(f)

elements = osm["elements"]

nodes = {}   # node_id  {lat, lon, tags}
ways = []    # routes utilisables (carrossables uniquement)

# Routes pour voitures -> on enleve les troitoirs , piste cyclable..etc
CARROSSABLE = [
    "motorway", "trunk", "primary", "secondary",
    "tertiary", "residential", "unclassified", "service"
]


# EXTRACTION DES NODES ET WAYS

for el in elements:
    if el["type"] == "node":
        nid = el["id"]
        # On ne veut pas écraser un node qui a des tags par un node sans tags (doublon d'Overpass)
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



# DÉTECTION DES INTERSECTIONS = nodes utilisés >= 2 fois

usage = {}
for way in ways:
    for nid in way["nodes"]:
        usage[nid] = usage.get(nid, 0) + 1

intersections = {nid for nid, count in usage.items() if count >= 2}



# CONSTRUCTION DES ROUTES (ID = way.id)
# + calcul de length + détermination de next intersection


def compute_length(node_list):
    total = 0
    for i in range(len(node_list) - 1):
        n1 = nodes[node_list[i]]
        n2 = nodes[node_list[i+1]]
        total += haversine(n1["lat"], n1["lon"], n2["lat"], n2["lon"])
    return total

# vitesses par défaut
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

roads = []
for way in ways:
    way_id = way["id"]
    nlist = way["nodes"]
    highway = way["tags"]["highway"]

    length = compute_length(nlist)

    # next = premier node de fin qui est une intersection
    next_inter = None
    for nid in nlist[::-1]:  # reverse
        if nid in intersections:
            next_inter = nid
            break

    roads.append({
        "id": way_id,
        "name": way["tags"].get("name", "Inconnue"),
        "length": length,
        "speed_limit": VITESSES.get(highway, 11.1),
        "oneway": way["tags"].get("oneway") == "yes",
        "nodes": nlist,
        "next": next_inter
    })



# CONSTRUCTION DES INTERSECTIONS (incoming/outgoing)


intersections_list = []

# initialisation
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

# remplissage des incoming/outgoing
for road in roads:
    r_id = road["id"]
    nlist = road["nodes"]

    start = None
    end = None

    # start = premier node intersection rencontré
    for nid in nlist:
        if nid in intersections:
            start = nid
            break

    # end = dernier node intersection rencontré
    for nid in reversed(nlist):
        if nid in intersections:
            end = nid
            break

    if start is not None and end is not None and start != end:
        inter_dict[start]["outgoing"].append(r_id)
        inter_dict[end]["incoming"].append(r_id)

intersections_list = list(inter_dict.values())


# EXTRACTION DES FEUX ET PASSAGES PIÉTONS SPÉCIFIQUES

signals_list = []
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



# EXPORT FINAL POUR LE SIMULATEUR

# On exporte aussi les coordonnées de tous les nodes pour pouvoir dessiner les routes avec leurs courbes
# On s'assure que les clés sont des chaînes pour la compatibilité JSON
nodes_coords = {str(nid): {"lat": ninfo["lat"], "lon": ninfo["lon"]} for nid, ninfo in nodes.items()}

output = {
    "roads": roads,
    "intersections": intersections_list,
    "feux": signals_list,
    "passages": crossings_list,
    "nodes": nodes_coords
}

file_path = os.path.join(os.path.dirname(__file__), "..", "data", "map_clean.json")
with open(file_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"{file_path} généré !")
print(f"{len(roads)} routes")
print(f"{len(intersections_list)} intersections")
print(f"{len(signals_list)} feux de circulation")
print(f"{len(crossings_list)} passages piétons")