"""Compare la baseline (cycles fixes) avec l'agent RL."""

import argparse
import json
import os

from rl.agent import load_agent
from rl.analysis import PhaseTracker, recommend, rank, print_ranking
from rl.env import ACTION_KEEP, TrafficRLEnv, default_map_path


# Cibles fixees dans le rapport intermediaire
CIBLE_TEMPS_TRAJET = 0.15
CIBLE_FILE         = 0.20
CIBLE_DEBIT        = 0.10


def baseline_policy(obs):
    return {gid: ACTION_KEEP for gid in obs}


def rl_policy(agent):
    def policy(obs):
        actions = {}
        for gid in obs:
            actions[gid] = agent.greedy_action(obs[gid]["state_tuple"])
        return actions
    return policy


def run_episode(env, policy, label, tracker):
    print(f"\n[{label}] simulation en cours...")
    obs = env.reset()
    tracker.reset(env.light_manager)
    done = False
    while not done:
        actions = policy(obs)
        obs, _r, done, info = env.step(actions, on_tick=tracker.tick)
    summary = env.summary()
    print(f"[{label}] termine : {info['total_arrived']} vehicules arrives "
          f"sur {summary['spawned']} crees en {summary['duration_s']:.1f}s")
    return summary


def _row(label, key, sens, cible, baseline, rl):
    b = float(baseline.get(key, 0.0))
    r = float(rl.get(key, 0.0))
    delta = 0.0 if b == 0.0 else (r - b) / b
    amelioration = -delta if sens == "lower" else delta
    return {
        "metric":      label,
        "key":         key,
        "baseline":    b,
        "rl":          r,
        "improvement": amelioration,
        "target":      cible,
        "passed":      amelioration >= cible,
    }


def compare(baseline, rl):
    rows = [
        _row("Temps moyen de trajet (s)", "avg_trip_time_s",
             "lower", CIBLE_TEMPS_TRAJET, baseline, rl),
        _row("File moyenne (veh)", "avg_queue_length",
             "lower", CIBLE_FILE, baseline, rl),
        _row("Debit (veh/min)", "throughput_per_min",
             "higher", CIBLE_DEBIT, baseline, rl),
    ]
    return {"rows": rows, "all_pass": all(r["passed"] for r in rows)}


def compare_robust(baseline, rl):
    """Indicateurs robustes au biais de selection :
    - trip median au lieu d'avg (insensible aux outliers)
    - vitesse moyenne (proxy direct de la fluidite)
    - attente aux feux (mesure pertinente pour la file)
    """
    rows = [
        _row("Trip median (s)", "median_trip_time_s",
             "lower", 0.05, baseline, rl),
        _row("Vitesse moyenne (m/s)", "avg_speed_m_s",
             "higher", 0.10, baseline, rl),
        _row("Attente moyenne aux feux (s)", "avg_light_wait_s",
             "lower", 0.15, baseline, rl),
        _row("Debit (veh/min)", "throughput_per_min",
             "higher", CIBLE_DEBIT, baseline, rl),
    ]
    return {"rows": rows, "all_pass": all(r["passed"] for r in rows)}


def print_report(comparison, title="Cibles officielles du rapport"):
    print("\n" + "=" * 78)
    print(title)
    print("-" * 78)
    print(f"{'Metrique':<32}{'Baseline':>12}{'RL':>12}"
          f"{'Variation':>12}{'Statut':>10}")
    print("-" * 78)
    for row in comparison["rows"]:
        # Variation reelle (RL - baseline) / baseline pour eviter le piege
        # ou le signe de l'amelioration est inverse pour "lower is better"
        if row["baseline"] != 0:
            real_var = (row["rl"] - row["baseline"]) / row["baseline"]
        else:
            real_var = 0.0
        sign = "+" if real_var >= 0 else "-"
        var = f"{sign}{abs(real_var) * 100:5.1f}%"
        status = "PASS" if row["passed"] else "FAIL"
        cible_str = f">= {row['target'] * 100:.0f}%"
        print(f"{row['metric']:<32}"
              f"{row['baseline']:>12.3f}"
              f"{row['rl']:>12.3f}"
              f"{var:>12}"
              f"{status + ' (' + cible_str + ')':>18}")
    print("-" * 78)
    print(f"Verdict : {'SUCCES GLOBAL' if comparison['all_pass'] else 'ECHEC GLOBAL'}")
    print("=" * 78)


def write_json(path, data, label):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n{label} : {path}")


def benchmark(qtable_path, max_time=300.0, target_vehicles=100,
              seed=42, output_path=None):
    if not os.path.isfile(qtable_path):
        raise FileNotFoundError(
            f"Q-table introuvable : {qtable_path}\n"
            f"Lancez d'abord : make rl-train"
        )

    print(f"Chargement de la Q-table : {qtable_path}")
    agent = load_agent(qtable_path)
    print(f"  {len(agent.Q)} etats memorises")

    common = dict(
        map_path=default_map_path(),
        step_dt=5.0,
        max_time=max_time,
        target_vehicles=target_vehicles,
        random_seed=seed,
    )

    env_b = TrafficRLEnv(**common)
    tracker_b = PhaseTracker()
    baseline = run_episode(env_b, baseline_policy, "Baseline", tracker_b)

    env_r = TrafficRLEnv(**common)
    tracker_r = PhaseTracker()
    rl_summary = run_episode(env_r, rl_policy(agent), "RL", tracker_r)

    comparison = compare(baseline, rl_summary)
    print_report(comparison, "Cibles officielles du rapport")

    robust = compare_robust(baseline, rl_summary)
    print_report(robust, "Indicateurs robustes (analyse complementaire)")

    light_to_group = {}
    for light in env_r.light_manager.get_all_lights():
        if light.group_id is not None:
            light_to_group[light.node_id] = light.group_id

    recommendations = recommend(
        tracker_r.stats(),
        baseline_per_light=baseline.get("per_light", {}),
        rl_per_light=rl_summary.get("per_light", {}),
        light_to_group=light_to_group,
    )
    ranking = rank(recommendations, top_n=10)
    print_ranking(ranking)

    results_dir = _results_dir()
    os.makedirs(results_dir, exist_ok=True)
    if output_path is None:
        output_path = os.path.join(results_dir, "benchmark.json")
    write_json(output_path,
               {"baseline": baseline, "rl": rl_summary,
                "comparison": comparison, "robust": robust},
               "Resultats detailles")
    write_json(os.path.join(results_dir, "recommended_cycles.json"),
               {"ranking": ranking, "recommendations": recommendations},
               "Recommandations")
    return comparison


def _results_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "results"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qtable", type=str,
                        default=os.path.join(_results_dir(), "q_table.json"))
    parser.add_argument("--max-time", type=float, default=300.0)
    parser.add_argument("--vehicles", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    benchmark(
        qtable_path=args.qtable,
        max_time=args.max_time,
        target_vehicles=args.vehicles,
        seed=args.seed,
        output_path=args.out,
    )


if __name__ == "__main__":
    main()
