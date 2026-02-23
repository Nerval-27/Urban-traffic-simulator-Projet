import os
from loader import load_network
from renderer import Renderer

def main():
    # Chemin vers le fichier JSON
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.normpath(os.path.join(current_dir, "..", "data", "map_clean.json"))
    
    print(f"Chargement du réseau : {json_path}...")
    try:
        network = load_network(json_path)
    except Exception as e:
        print(f"Erreur lors du chargement : {e}")
        return

    print(f"Réseau chargé : {len(network.roads)} routes, {len(network.intersections)} intersections.")
    print(f"Feux : {len(network.feux)}, Passages piétons : {len(network.passages)}")
    print("Démarrage du visualiseur Pygame...")

    # Initialisation et lancement du moteur de rendu
    renderer = Renderer(network)
    renderer.run()

if __name__ == "__main__":
    main()
