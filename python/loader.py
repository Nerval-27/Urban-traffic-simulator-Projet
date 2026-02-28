import json
from models import Road, Intersection, Network, TrafficSignal, PedestrianCrossing

def parse_road(data):
    """Convertit un dictionnaire JSON en objet Road."""
    return Road(
        id=int(data["id"]),
        name=data.get("name", "Inconnue"),
        length=float(data["length"]),
        speed_limit=float(data["speed_limit"]),
        nodes=[int(n) for n in data["nodes"]],
        next=int(data["next"]) if data["next"] is not None else -1,
        oneway=data.get("oneway", False)
    )

def parse_intersection(data):
    """Convertit un dictionnaire JSON en objet Intersection."""
    return Intersection(
        id=int(data["id"]),
        lat=float(data["lat"]),
        lon=float(data["lon"]),
        incoming=[int(r) for r in data["incoming"]],
        outgoing=[int(r) for r in data["outgoing"]],
        light_state=[] 
    )

def parse_signal(data):
    return TrafficSignal(id=data["id"], lat=data["lat"], lon=data["lon"])

def parse_crossing(data):
    return PedestrianCrossing(
        id=data["id"], 
        lat=data["lat"], 
        lon=data["lon"], 
        is_regulated=data.get("is_regulated", False)
    )

def load_network(filename):
    """Charge le réseau complet depuis un fichier JSON."""
    with open(filename, 'r') as f:
        data = json.load(f)
    
    roads = [parse_road(r) for r in data.get("roads", [])]
    intersections = [parse_intersection(i) for i in data.get("intersections", [])]
    signals = [parse_signal(s) for s in data.get("feux", [])]
    passages = [parse_crossing(c) for c in data.get("passages", [])]
    
    # Mapping des nodes
    nodes = {}
    if "nodes" in data:
        for nid, coords in data["nodes"].items():
            nodes[int(nid)] = (coords["lat"], coords["lon"])

    return Network(
        roads=roads,
        intersections=intersections,
        feux=signals,
        passages=passages,
        nodes=nodes
    )
