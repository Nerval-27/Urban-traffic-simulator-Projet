import sys
import os
from loader import load_network

def main():
    print("=== Traffic Simulator ===")
    
    # Chemin vers le fichier JSON
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.normpath(os.path.join(current_dir, "..", "data", "map_clean.json"))
    
    print(f"Chargement du fichier : {json_path}")
    
    try:
        network = load_network(json_path)
    except Exception as e:
        print(f"Erreur réelle : {e}")
        sys.exit("Chargement JSON échoué")
    
    print(f" Réseau chargé : {len(network.roads)} routes")
    print(f" Intersections chargées : {len(network.intersections)} intersections")
    print(f" Feux de circulation : {len(network.feux)}")
    print(f" Passages piétons : {len(network.passages)}")

    print("Initialisation des véhicules (non implémentée)")

    # 3. Boucle de simulation
    steps = 10
    for t in range(steps + 1):
        print(f"Tick {t}...")
        # plus tard : update positions, collisions, lights, etc.
    
    print("Simulation terminée.")

if __name__ == "__main__":
    main()
