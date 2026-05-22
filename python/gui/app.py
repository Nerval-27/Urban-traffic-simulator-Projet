import argparse
import os
import sys
import random
import pygame

from simulation.loader import load_network
from simulation.graph import RoadGraph
from simulation.lights import TrafficLightManager
from simulation.vehicle import VehicleManager
from simulation.metrics import TrafficMetrics
from gui.renderer import Renderer



INITIAL_VEHICLE_COUNT = 15
MAX_VEHICLES          = 150
SPAWN_INTERVAL        = 3
TARGET_VEHICLES       = 1000
SIM_SPEED_DEFAULT     = 1.0
SIM_SPEED_MIN         = 0.25
SIM_SPEED_MAX         = 8.0
RANDOM_SEED           = 42
METRIC_SAMPLE_INTERVAL = 1.0
RL_STEP_DT            = 5.0    # l'agent décide toutes les 5s simulées
DEFAULT_QTABLE_PATH   = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "results", "q_table.json")
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fixed", "rl"), default="fixed",
                        help="Stratégie des feux : fixed (cycles fixes) ou rl (Q-learning)")
    parser.add_argument("--qtable", type=str, default=DEFAULT_QTABLE_PATH,
                        help="Chemin de la Q-table (mode rl uniquement)")
    args = parser.parse_args()

    traffic_mode = args.mode

    print("=" * 50)
    print("   Paris 13e — Traffic Simulator")
    print(f"   Mode feux : {traffic_mode.upper()}")
    print("=" * 50)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.normpath(os.path.join(current_dir, "..", "..", "data", "map_clean.json"))

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

    metrics = TrafficMetrics(sample_interval=METRIC_SAMPLE_INTERVAL)

    rl_controller = None
    if traffic_mode == "rl":
        rl_controller = _build_rl_controller(args.qtable, light_manager, metrics)
        if rl_controller is None:
            sys.exit(1)

    print("\nDémarrage de la simulation Pygame...")
    renderer = Renderer(network, width=1280, height=720)
    renderer.vehicle_manager = vehicle_manager
    renderer.light_manager   = light_manager
    renderer.graph           = graph
    renderer.sim_speed       = SIM_SPEED_DEFAULT
    renderer.metrics         = metrics
    renderer.traffic_mode    = traffic_mode
    renderer.rl_controller   = rl_controller

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
        metrics.update(sim_dt, vehicle_manager, light_manager)

        if rl_controller is not None:
            rl_controller.tick(sim_dt)

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
            _print_final_stats(vehicle_manager, light_manager, metrics, sim_time)
            if rl_controller is not None:
                _print_rl_stats(rl_controller)
            _export_metrics(metrics, current_dir, traffic_mode)
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


def _print_final_stats(vehicle_manager, light_manager, metrics, sim_time):
    stats = vehicle_manager.get_stats()
    metric_summary = metrics.summary()
    mins  = int(sim_time) // 60
    secs  = int(sim_time) % 60
    print("\nStatistiques finales")
    print(f"  Durée simulée   : {mins:02d}:{secs:02d}")
    print(f"  Véhicules créés : {stats['spawned']}")
    print(f"  Arrivés à dest. : {stats['arrived']}")
    print(f"  Débit           : {metric_summary['throughput_per_min']} véhicules/min")
    print(f"  File moyenne    : {metric_summary['avg_queue_length']} véhicules")
    print(f"  File maximale   : {metric_summary['max_queue_length']} véhicules")
    print(f"  Saturation max  : {metrics.live_stats()['max_saturation']}")

    waiting_stats = light_manager.get_waiting_stats()
    total_stops = sum(waiting_stats.values())
    print(f"  Arrêts aux feux : {total_stops}")
    congested = light_manager.get_congested_lights(threshold=5)
    print(f"  Feux congestionnés (>5 arrêts) : {len(congested)}")
    print()


def _build_rl_controller(qtable_path, light_manager, metrics):
    """Charge la Q-table et construit un RLController prêt à brancher."""
    if not os.path.isfile(qtable_path):
        print(f"ERREUR : Q-table introuvable ({qtable_path})")
        print("Lancez d'abord : make rl-train")
        return None

    from rl.agent import load_agent
    from rl.env import RLController

    print(f"\nChargement de la Q-table : {qtable_path}")
    agent = load_agent(qtable_path)
    print(f"  {len(agent.Q)} états mémorisés")

    return RLController(agent, light_manager, metrics, step_dt=RL_STEP_DT)


def _print_rl_stats(rl_controller):
    stats = rl_controller.stats()
    print("Agent RL")
    print(f"  Q-table         : {stats['qtable_size']} états")
    print(f"  Pas de décision : {stats['step_dt']:.1f}s")
    print(f"  Décisions KEEP  : {stats['keep_count']}")
    print(f"  Décisions SWITCH: {stats['switch_count']} "
          f"({stats['switch_ratio'] * 100:.1f}%)")
    print()


def _export_metrics(metrics, current_dir, mode):
    results_dir = os.path.normpath(os.path.join(current_dir, "..", "..", "results"))
    os.makedirs(results_dir, exist_ok=True)

    summary_path = os.path.join(results_dir, f"{mode}_summary.json")
    snapshots_path = os.path.join(results_dir, f"{mode}_snapshots.csv")
    observation_path = os.path.join(results_dir, f"{mode}_observation.json")

    metrics.write_summary_json(summary_path)
    metrics.write_snapshots_csv(snapshots_path)
    metrics.write_observation_json(observation_path)

    print(f"  Métriques JSON  : {summary_path}")
    print(f"  Métriques CSV   : {snapshots_path}")


if __name__ == "__main__":
    main()
