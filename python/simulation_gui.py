import os
import sys
import random
import pygame

from loader import load_network
from graph import RoadGraph
from traffic_light_manager import TrafficLightManager
from vehicle import VehicleManager
from renderer import Renderer



INITIAL_VEHICLE_COUNT = 15
MAX_VEHICLES          = 150
SPAWN_INTERVAL        = 3
TARGET_VEHICLES       = 1000
SIM_SPEED_DEFAULT     = 1.0
SIM_SPEED_MIN         = 0.25
SIM_SPEED_MAX         = 8.0
RANDOM_SEED           = 42


def main():
    print("=" * 50)
    print("   Paris 13e — Traffic Simulator")
    print("=" * 50)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.normpath(os.path.join(current_dir, "..", "data", "map_clean.json"))

    print(f"\n[1/4] Chargement du réseau : {json_path}")
    try:
        network = load_network(json_path)
    except FileNotFoundError:
        print(f"ERREUR : Fichier introuvable  {json_path}")
        print("Lancez d'abord fetch_osm.py puis clean_json.py pour générer map_clean.json")
        sys.exit(1)
    except Exception as e:
        print(f"ERREUR lors du chargement : {e}")
        sys.exit(1)

    print(f"  {len(network.roads)} routes, {len(network.intersections)} intersections")
    print(f"  {len(network.feux)} feux, {len(network.passages)} passages piétons")
    print(f"  {len(network.nodes)} noeuds OSM")

    print("\n[2/4] Construction du graphe routier...")
    graph = RoadGraph()
    graph.build_from_network(network)
    print(f"  {graph.node_count()} nœuds, {graph.edge_count()} arcs")

    if graph.node_count() == 0:
        print("ERREUR : Le graphe est vide. Vérifiez map_clean.json.")
        sys.exit(1)

    print("\n[3/4] Initialisation des feux de circulation...")
    light_manager = TrafficLightManager()
    light_manager.build_from_graph(graph)

    print("\n[4/4] Initialisation des véhicules...")
    rng = random.Random(RANDOM_SEED)
    vehicle_manager = VehicleManager(graph, light_manager, rng=rng)
    vehicle_manager.build_edge_index()
    created = vehicle_manager.spawn_batch(INITIAL_VEHICLE_COUNT)
    print(f"  {created} véhicules créés sur {INITIAL_VEHICLE_COUNT} demandés")

    print("\nDémarrage de la simulation Pygame...")
    renderer = Renderer(network, width=1280, height=720)
    renderer.vehicle_manager = vehicle_manager
    renderer.light_manager   = light_manager
    renderer.graph           = graph
    renderer.sim_speed       = SIM_SPEED_DEFAULT

    sim_time       = 0.0
    spawn_timer    = 0.0
    sim_speed      = SIM_SPEED_DEFAULT
    clock          = renderer.clock

    print("\nSimulation en cours. (Appuyez sur Échap pour quitter)\n")
    print("  N   spawner un véhicule")
    print("  +   accélérer la simulation")
    print("  -   ralentir la simulation")
    print("  R   reset de la vue\n")

    while True:
        real_dt = clock.tick(60) / 1000.0
        real_dt = min(real_dt, 0.05)

        sim_dt = real_dt * sim_speed

        light_manager.update(sim_dt)
        vehicle_manager.update(sim_dt)

        sim_time   += sim_dt
        spawn_timer += sim_dt

        if spawn_timer >= SPAWN_INTERVAL:
            spawn_timer = 0.0
            active = vehicle_manager.get_active_count()
            if active < TARGET_VEHICLES and active < MAX_VEHICLES:
                to_spawn = min(TARGET_VEHICLES - active,
                               MAX_VEHICLES - active,
                               10)
                vehicle_manager.spawn_batch(to_spawn)

        renderer.simulation_time = sim_time
        renderer.sim_speed       = sim_speed

        actions = renderer.handle_events()

        if actions.get("quit"):
            print("\nSimulation arrêtée.")
            _print_final_stats(vehicle_manager, light_manager, sim_time)
            pygame.quit()
            sys.exit(0)

        if actions.get("speed_up"):
            sim_speed = min(SIM_SPEED_MAX, sim_speed * 2.0)
            print(f"[Sim] Vitesse × {sim_speed:.1f}")

        if actions.get("speed_down"):
            sim_speed = max(SIM_SPEED_MIN, sim_speed / 2.0)
            print(f"[Sim] Vitesse × {sim_speed:.1f}")

        if actions.get("spawn"):
            v = vehicle_manager.spawn_vehicle()
            if v:
                print(f"[Sim] Véhicule #{v.vehicle_id} spawné")

        renderer.draw()


def _print_final_stats(vehicle_manager, light_manager, sim_time):
    stats = vehicle_manager.get_stats()
    mins  = int(sim_time) // 60
    secs  = int(sim_time) % 60
    print("\nStatistiques finales")
    print(f"  Durée simulée   : {mins:02d}:{secs:02d}")
    print(f"  Véhicules créés : {stats['spawned']}")
    print(f"  Arrivés à dest. : {stats['arrived']}")

    waiting_stats = light_manager.get_waiting_stats()
    total_stops = sum(waiting_stats.values())
    print(f"  Arrêts aux feux : {total_stops}")
    congested = light_manager.get_congested_lights(threshold=5)
    print(f"  Feux congestionnés (>5 arrêts) : {len(congested)}")
    print()


if __name__ == "__main__":
    main()
