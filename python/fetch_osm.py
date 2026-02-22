import requests
import json

query = """
[out:json];
area["name"="Paris 13e Arrondissement"]["admin_level"="9"]->.search;
(
  way["highway"](area.search);
  node["highway"="traffic_signals"](area.search);
  node["highway"="crossing"]["crossing"="traffic_signals"](area.search);
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

print("➡️ Status:", r.status_code)

if r.status_code != 200:
    print("Erreur:", r.text)
    exit()

data = r.json()

if r.status_code == 429:
    print(" Rate limit atteint, attente 30 secondes...")
    time.sleep(30)

with open("../data/paris13.json", "w") as f:
    json.dump(data, f, indent=2)

print("Données sauvegardées dans paris13.json")