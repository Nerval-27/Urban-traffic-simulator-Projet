import json
import sys
import math
from utils import haversine


# LECTURE DU FICHIER OSM

if len(sys.argv) < 2:
    exit()

osm_file = sys.argv[1]

with open(osm_file, "r") as f:
    osm = json.load(f)

elements = osm["elements"]

nodes = {}   # node_id → {lat, lon, tags}
ways = []    # routes utilisables (carrossables uniquement)

# Routes pour voitures -> on enleve les troitoirs , piste cyclable..etc
CARROSSABLE = [
    "motorway", "trunk", "primary", "secondary",
    "tertiary", "residential", "unclassified", "service"
]


# EXTRACTION DES NODES ET WAYS

for el in elements:
    if el["type"] == "node":
        nodes[el["id"]] = {
            "lat": el["lat"],
            "lon": el["lon"],
            "tags": el.get("tags", {})
        }

    elif el["type"] == "way":
        highway = el.get("tags", {}).get("highway")
        if highway in CARROSSABLE:
            ways.append(el)



# DÉTECTION DES INTERSECTIONS = nodes utilisés ≥ 2 fois

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

# vitesse par défaut selon type de route
SPEED_LIMITS = {
    "motorway": 33.3,     # 120 km/h 
    "trunk": 27.7,        # 100 km/h
    "primary": 22.2,      # 80 km/h
    "secondary": 16.6,    # 60 km/h
    "tertiary": 13.8,     # 50 km/h
    "residential": 11.1,  # 40 km/h
    "unclassified": 11.1,
    "service": 8.3        # 30 km/h
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
        "length": length,
        "speed_limit": SPEED_LIMITS[highway],
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
        "has_light": ("traffic_signals" in nodes[nid].get("tags", {})),
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



# EXPORT FINAL POUR OCAML

output = {
    "roads": roads,
    "intersections": intersections_list
}

with open("../data/map_clean.json", "w") as f:
    json.dump(output, f, indent=2)

print("map_clean.json généré !")
print(f"{len(roads)} routes")
print(f"{len(intersections_list)} intersections")