import json
from models import Road, Intersection, Network

def parse_road(data):
    """Convertit un dictionnaire JSON en objet Road."""
    return Road(
        id=int(data["id"]),
        length=float(data["length"]),
        speed_limit=float(data["speed_limit"]),
        nodes=[int(n) for n in data["nodes"]],
        next=int(data["next"]) if data["next"] is not None else -1
    )

def parse_intersection(data):
    """Convertit un dictionnaire JSON en objet Intersection."""
    return Intersection(
        id=int(data["id"]),
        incoming=[int(r) for r in data["incoming"]],
        outgoing=[int(r) for r in data["outgoing"]],
        light_state=[]
    )

def load_network(filename):
    """Charge le réseau complet depuis un fichier JSON."""
    with open(filename, 'r') as f:
        data = json.load(f)
    
    roads = [parse_road(r) for r in data.get("roads", [])]
    intersections = [parse_intersection(i) for i in data.get("intersections", [])]
    
    return Network(
        roads=roads,
        intersections=intersections
    )
