"""Compare la baseline (cycles fixes) avec l'agent RL.

Lance 2 simulations identiques (meme seed, memes vehicules) :
- baseline : agent fait toujours KEEP
- rl       : agent applique sa politique greedy
Et compare sur les 3 metriques du rapport.
"""

import argparse
import json
import os
from statistics import mean, stdev

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


def print_report(comparison):
    print("\n" + "=" * 78)
    print(f"{'Metrique':<28}{'Baseline':>12}{'RL':>12}"
          f"{'Variation':>14}{'Statut':>12}")
    print("-" * 78)
    for row in comparison["rows"]:
        sign = "+" if row["improvement"] >= 0 else "-"
        var = f"{sign}{abs(row['improvement']) * 100:5.1f}%"
        status = "PASS" if row["passed"] else "FAIL"
        cible_str = f">= {row['target'] * 100:.0f}%"
        print(f"{row['metric']:<28}"
              f"{row['baseline']:>12.3f}"
              f"{row['rl']:>12.3f}"
              f"{var:>14}"
              f"{status + ' (' + cible_str + ')':>20}")
    print("-" * 78)
    print(f"Verdict : {'SUCCES GLOBAL' if comparison['all_pass'] else 'ECHEC GLOBAL'}")
    print("=" * 78)


def write_json(path, data, label):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n{label} : {path}")


def _numeric_average(rows, key):
    values = [float(row.get(key, 0.0)) for row in rows]
    return mean(values) if values else 0.0


def _numeric_stdev(rows, key):
    values = [float(row.get(key, 0.0)) for row in rows]
    return stdev(values) if len(values) >= 2 else 0.0


def _aggregate_summaries(rows):
    keys = [
        "duration_s",
        "spawned",
        "arrived",
        "active",
        "completion_rate",
        "throughput_per_min",
        "avg_trip_time_s",
        "median_trip_time_s",
        "avg_queue_length",
        "max_queue_length",
        "avg_waiting_at_lights",
        "max_waiting_at_light",
        "avg_light_wait_s",
        "avg_wait_time_per_spawned_s",
        "avg_stop_time_per_spawned_s",
        "avg_speed_m_s",
        "congestion_ratio",
    ]
    return {key: round(_numeric_average(rows, key), 3) for key in keys}


def _aggregate_spread(rows):
    keys = [
        "throughput_per_min",
        "avg_trip_time_s",
        "avg_queue_length",
        "avg_light_wait_s",
        "congestion_ratio",
    ]
    return {key: round(_numeric_stdev(rows, key), 3) for key in keys}


def _parse_seeds(value):
    if isinstance(value, (list, tuple)):
        return [int(v) for v in value]
    return [int(part.strip()) for part in str(value).split(",") if part.strip()]


def _run_pair(agent, common, seed, run_index):
    env_b = TrafficRLEnv(**common, random_seed=seed)
    tracker_b = PhaseTracker()
    baseline = run_episode(env_b, baseline_policy,
                           f"Baseline seed={seed}", tracker_b)

    env_r = TrafficRLEnv(**common, random_seed=seed)
    tracker_r = PhaseTracker()
    rl_summary = run_episode(env_r, rl_policy(agent),
                             f"RL seed={seed}", tracker_r)

    return {
        "run": run_index,
        "seed": seed,
        "baseline": baseline,
        "rl": rl_summary,
        "tracker": tracker_r,
        "light_manager": env_r.light_manager,
    }


def benchmark(qtable_path, max_time=300.0, target_vehicles=100,
              seed=42, seeds=None, output_path=None):
    if not os.path.isfile(qtable_path):
        raise FileNotFoundError(
            f"Q-table introuvable : {qtable_path}\n"
            f"Lancez d'abord : make rl-train"
        )

    print(f"Chargement de la Q-table : {qtable_path}")
    agent = load_agent(qtable_path)
    print(f"  {len(agent.Q)} etats memorises")

    seed_values = _parse_seeds(seeds if seeds is not None else seed)

    common = dict(
        map_path=default_map_path(),
        step_dt=5.0,
        max_time=max_time,
        target_vehicles=target_vehicles,
    )

    runs = [
        _run_pair(agent, common, seed_value, idx + 1)
        for idx, seed_value in enumerate(seed_values)
    ]

    baseline = _aggregate_summaries([run["baseline"] for run in runs])
    rl_summary = _aggregate_summaries([run["rl"] for run in runs])

    comparison = compare(baseline, rl_summary)
    print_report(comparison)

    spread = {
        "baseline": _aggregate_spread([run["baseline"] for run in runs]),
        "rl": _aggregate_spread([run["rl"] for run in runs]),
    }

    last_run = runs[-1]
    light_to_group = {}
    for light in last_run["light_manager"].get_all_lights():
        if light.group_id is not None:
            light_to_group[light.node_id] = light.group_id

    recommendations = recommend(
        last_run["tracker"].stats(),
        baseline_per_light=last_run["baseline"].get("per_light", {}),
        rl_per_light=last_run["rl"].get("per_light", {}),
        light_to_group=light_to_group,
    )
    ranking = rank(recommendations, top_n=10)
    print_ranking(ranking)

    results_dir = _results_dir()
    os.makedirs(results_dir, exist_ok=True)
    if output_path is None:
        output_path = os.path.join(results_dir, "benchmark.json")
    write_json(output_path,
               {
                   "seeds": seed_values,
                   "runs": [
                       {
                           "seed": run["seed"],
                           "baseline": run["baseline"],
                           "rl": run["rl"],
                           "comparison": compare(run["baseline"], run["rl"]),
                       }
                       for run in runs
                   ],
                   "baseline": baseline,
                   "rl": rl_summary,
                   "spread": spread,
                   "comparison": comparison,
               },
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
    parser.add_argument("--seeds", type=str, default=None,
                        help="Liste de seeds separees par des virgules, ex: 42,43,44")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    benchmark(
        qtable_path=args.qtable,
        max_time=args.max_time,
        target_vehicles=args.vehicles,
        seed=args.seed,
        seeds=args.seeds,
        output_path=args.out,
    )


if __name__ == "__main__":
    main()
