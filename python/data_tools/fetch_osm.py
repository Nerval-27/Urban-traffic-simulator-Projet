import requests
import json
import os
import time

query = """
[out:json];
area["name"="Paris 13e Arrondissement"]["admin_level"="9"]->.search;
(
  way["highway"](area.search);
  node["highway"="traffic_signals"](area.search);
  node["highway"="crossing"](area.search);
);
out body;
>;
out skel qt;
"""

print("Envoi requête Overpass (Paris 13e)...")

r = requests.get(
    "https://overpass-api.de/api/interpreter",
    params={"data": query}
)

print("Status:", r.status_code)

if r.status_code != 200:
    print("Erreur:", r.text)
    exit()

data = r.json()

if r.status_code == 429:
    print("Trop de requêtes, on attend un peu...")
    time.sleep(30)

file_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "paris13.json")
with open(file_path, "w") as f:
    json.dump(data, f, indent=2)

print(f"Données sauvegardées dans {file_path}")