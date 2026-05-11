"""Smoke test : politique aleatoire pour verifier que l'env tourne."""

import random

from rl.env import NB_ACTIONS, TrafficRLEnv, default_map_path


def main():
    print("Initialisation de l'environnement RL...")
    env = TrafficRLEnv(
        map_path=default_map_path(),
        step_dt=5.0,
        max_time=60.0,
        initial_vehicles=15,
        target_vehicles=80,
    )

    obs = env.reset()
    print(f"Groupes détectés : {len(env.group_ids())}")
    print("Observation initiale (3 premiers groupes) :")
    for gid in env.group_ids()[:3]:
        o = obs[gid]
        print(f"  groupe {gid:>3}  queue_A={o['queue_A']:>2} queue_B={o['queue_B']:>2}"
              f"  phase={o['phase']}/{o['state']}"
              f"  state_tuple={o['state_tuple']}")

    rng = random.Random(0)
    total_steps = 0
    score = 0.0
    done = False
    while not done:
        actions = {gid: rng.randrange(NB_ACTIONS) for gid in env.group_ids()}
        obs, rewards, done, info = env.step(actions)
        total_steps += 1
        score += sum(rewards.values())

        if total_steps % 4 == 0 or done:
            mean_r = sum(rewards.values()) / max(1, len(rewards))
            print(f"  step {total_steps:>2}  t={info['sim_time']:5.1f}s"
                  f"  arrivés={info['total_arrived']:>3}"
                  f"  actifs={info['total_active']:>3}"
                  f"  reward moyen={mean_r:+.2f}")

    print(f"\nRésumé final après {total_steps} steps :")
    summary = env.summary()
    print(f"  Durée            : {summary['duration_s']:.1f}s")
    print(f"  Véhicules créés  : {summary['spawned']}")
    print(f"  Véhicules arrivés: {summary['arrived']}")
    print(f"  Débit            : {summary['throughput_per_min']} véh/min")
    print(f"  File moyenne     : {summary['avg_queue_length']}")
    print(f"  Attente moyenne  : {summary['avg_light_wait_s']}s")
    print(f"  Score cumulé     : {score:+.2f}")


if __name__ == "__main__":
    main()
