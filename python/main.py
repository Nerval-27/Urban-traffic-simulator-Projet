
import sys
import os
import random

from simulation.loader import load_network
from simulation.graph import RoadGraph
from simulation.lights import TrafficLightManager
from simulation.vehicle import VehicleManager


def main():
    print("Traffic Simulator (mode console)\n")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.normpath(os.path.join(current_dir, "..", "data", "map_clean.json"))

    print(f"Chargement : {json_path}")
    try:
        network = load_network(json_path)
    except FileNotFoundError:
        print("ERREUR : map_clean.json introuvable.")
        print("Lancez d'abord : make data")
        sys.exit(1)

    print(f"  {len(network.roads)} routes, {len(network.intersections)} intersections")
    print(f"  {len(network.feux)} feux, {len(network.passages)} passages piétons")

    print("\nConstruction du graphe...")
    graph = RoadGraph()
    graph.build_from_network(network)
    print(f"  {graph.node_count()} nœuds, {graph.edge_count()} arcs")

    print("\nInitialisation des feux...")
    light_manager = TrafficLightManager()
    light_manager.build_from_graph(graph)

    print("\nCréation des véhicules...")
    rng = random.Random(42)
    vm = VehicleManager(graph, light_manager, rng=rng)
    vm.build_edge_index()
    created = vm.spawn_batch(10)
    print(f"  {created} véhicules créés")

    print("\nSimulation de 10 secondes...")
    dt = 0.1
    for tick in range(100):
        light_manager.update(dt)
        vm.update(dt)

    stats = vm.get_stats()
    print(f"\nRésultats après 10s :")
    print(f"  Véhicules actifs   : {stats['total']}")
    print(f"  En mouvement       : {stats['moving']}")
    print(f"  À l'arrêt          : {stats['stopped']}")
    print(f"  Arrivés            : {stats['arrived']}")



if __name__ == "__main__":
    main()
