"""Compare la baseline (cycles fixes) avec l'agent RL.

Supporte le benchmark sur plusieurs seeds (rigueur scientifique : on evite
qu'un coup de chance sur un seul scenario ne masque la realite). Les
metriques finales sont la moyenne sur tous les seeds.
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
    return _build_verdict(rows)


def _build_verdict(rows):
    """Construit un verdict nuance plutot que binaire.

    On classe selon 4 niveaux :
    - SUCCES GLOBAL : toutes les cibles atteintes
    - SUCCES MAJORITAIRE : plus de la moitie + toutes vont dans le bon sens
    - PROGRES PARTIEL : au moins une cible atteinte
    - ECHEC : aucune cible atteinte ou regression
    """
    n_total    = len(rows)
    n_passed   = sum(1 for r in rows if r["passed"])
    n_positive = sum(1 for r in rows if r["improvement"] > 0)

    if n_passed == n_total:
        verdict = "SUCCES GLOBAL"
    elif n_passed >= (n_total + 1) // 2 and n_positive == n_total:
        verdict = "SUCCES MAJORITAIRE"
    elif n_passed >= 1 and n_positive == n_total:
        verdict = "PROGRES PARTIEL"
    elif n_positive == n_total:
        verdict = "PROGRES DETECTE (sous cible)"
    else:
        verdict = "ECHEC"

    return {
        "rows":      rows,
        "passed":    n_passed,
        "total":     n_total,
        "all_pass":  n_passed == n_total,
        "verdict":   verdict,
    }


def compare_robust(baseline, rl):
    """Indicateurs robustes au biais de selection."""
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
    return _build_verdict(rows)


def print_report(comparison, title="Cibles officielles du rapport"):
    print("\n" + "=" * 78)
    print(title)
    print("-" * 78)
    print(f"{'Metrique':<32}{'Baseline':>12}{'RL':>12}"
          f"{'Variation':>12}{'Statut':>10}")
    print("-" * 78)
    for row in comparison["rows"]:
        # Variation reelle (RL - baseline) / baseline. Le signe correspond
        # toujours a la direction reelle de la variation, pas au sens du
        # critere d'amelioration (qui est dans PASS/FAIL).
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
    score = f"{comparison['passed']}/{comparison['total']} cibles atteintes"
    print(f"Verdict : {comparison['verdict']}  ({score})")
    print("=" * 78)


def write_json(path, data, label):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n{label} : {path}")


# Moyenne et ecart-type d'une serie de summaries (un par seed)

def _average_summaries(summaries):
    keys = [
        "duration_s", "spawned", "arrived", "active",
        "completion_rate", "throughput_per_min",
        "avg_trip_time_s", "median_trip_time_s",
        "avg_queue_length", "max_queue_length",
        "avg_waiting_at_lights", "max_waiting_at_light",
        "avg_light_wait_s", "avg_wait_time_per_spawned_s",
        "avg_stop_time_per_spawned_s",
        "avg_speed_m_s", "congestion_ratio",
    ]
    out = {}
    for key in keys:
        values = [float(s.get(key, 0.0)) for s in summaries]
        out[key] = round(mean(values), 3) if values else 0.0
    return out


def _stdev_summaries(summaries, keys):
    out = {}
    for key in keys:
        values = [float(s.get(key, 0.0)) for s in summaries]
        out[key] = round(stdev(values), 3) if len(values) >= 2 else 0.0
    return out


def _parse_seeds(value):
    if isinstance(value, (list, tuple)):
        return [int(v) for v in value]
    return [int(x.strip()) for x in str(value).split(",") if x.strip()]


def benchmark(qtable_path, max_time=300.0, target_vehicles=100,
              seeds=(42,), output_path=None):
    if not os.path.isfile(qtable_path):
        raise FileNotFoundError(
            f"Q-table introuvable : {qtable_path}\n"
            f"Lancez d'abord : make rl-train"
        )

    seed_list = _parse_seeds(seeds)
    print(f"Chargement de la Q-table : {qtable_path}")
    agent = load_agent(qtable_path)
    print(f"  {len(agent.Q)} etats memorises")
    print(f"  benchmark sur {len(seed_list)} seed(s) : {seed_list}")

    baseline_runs = []
    rl_runs = []
    last_tracker_rl = None
    last_env_r = None

    for idx, seed in enumerate(seed_list, start=1):
        print(f"\n--- Seed {seed} ({idx}/{len(seed_list)}) ---")
        common = dict(
            map_path=default_map_path(),
            step_dt=5.0,
            max_time=max_time,
            target_vehicles=target_vehicles,
            random_seed=seed,
        )

        env_b = TrafficRLEnv(**common)
        tracker_b = PhaseTracker()
        baseline = run_episode(env_b, baseline_policy,
                               f"Baseline seed={seed}", tracker_b)
        baseline_runs.append(baseline)

        env_r = TrafficRLEnv(**common)
        tracker_r = PhaseTracker()
        rl_summary = run_episode(env_r, rl_policy(agent),
                                 f"RL seed={seed}", tracker_r)
        rl_runs.append(rl_summary)

        last_tracker_rl = tracker_r
        last_env_r = env_r

    # Moyennes sur tous les seeds
    baseline_avg = _average_summaries(baseline_runs)
    rl_avg = _average_summaries(rl_runs)

    spread_keys = ["throughput_per_min", "avg_trip_time_s",
                   "avg_queue_length", "avg_light_wait_s"]
    spread = {
        "baseline": _stdev_summaries(baseline_runs, spread_keys),
        "rl":       _stdev_summaries(rl_runs, spread_keys),
    }

    comparison = compare(baseline_avg, rl_avg)
    print_report(comparison, "Cibles officielles du rapport (moyenne sur seeds)")

    robust = compare_robust(baseline_avg, rl_avg)
    print_report(robust, "Indicateurs robustes (moyenne sur seeds)")

    # Recommandations construites a partir du dernier run RL
    light_to_group = {}
    for light in last_env_r.light_manager.get_all_lights():
        if light.group_id is not None:
            light_to_group[light.node_id] = light.group_id

    recommendations = recommend(
        last_tracker_rl.stats(),
        baseline_per_light=baseline_runs[-1].get("per_light", {}),
        rl_per_light=rl_runs[-1].get("per_light", {}),
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
                   "seeds":      seed_list,
                   "baseline":   baseline_avg,
                   "rl":         rl_avg,
                   "spread":     spread,
                   "per_seed": [
                       {"seed": s, "baseline": b, "rl": r}
                       for s, b, r in zip(seed_list, baseline_runs, rl_runs)
                   ],
                   "comparison": comparison,
                   "robust":     robust,
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
    parser.add_argument("--seeds", type=str, default="42",
                        help="Une seed ou plusieurs separees par virgule (ex: 42,43,44)")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    benchmark(
        qtable_path=args.qtable,
        max_time=args.max_time,
        target_vehicles=args.vehicles,
        seeds=args.seeds,
        output_path=args.out,
    )


if __name__ == "__main__":
    main()
