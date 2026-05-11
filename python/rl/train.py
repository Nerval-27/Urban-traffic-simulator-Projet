"""Entrainement de l'agent Q-learning."""

import argparse
import os

from rl.agent import QLearningAgent
from rl.env import TrafficRLEnv, default_map_path


# 4 bins file_A * 4 bins file_B * 5 phases * 3 bins temps
TOTAL_ETATS = 4 * 4 * 5 * 3


def train(nb_episodes=30, max_time=120.0, target_vehicles=80, output_path=None):

    env = TrafficRLEnv(
        map_path=default_map_path(),
        step_dt=5.0,
        max_time=max_time,
        target_vehicles=target_vehicles,
    )

    agent = QLearningAgent(
        alpha=0.1,
        gamma=0.9,
        epsilon=1.0,
        epsilon_min=0.05,
        epsilon_decay=0.92,
    )

    print(f"\nEntrainement Q-learning : {nb_episodes} episodes "
          f"de {max_time:.0f}s simulees.\n")
    print(f"{'ep':>4} {'eps':>6} {'reward':>10} {'arrived':>8}"
          f" {'avg_queue':>10} {'states':>8}")

    for episode in range(1, nb_episodes + 1):
        obs = env.reset()
        score = 0.0
        done = False

        while not done:
            actions = {gid: agent.choose(obs[gid]["state_tuple"])
                       for gid in env.group_ids()}
            next_obs, rewards, done, _info = env.step(actions)

            for gid in env.group_ids():
                agent.update(
                    state=obs[gid]["state_tuple"],
                    action=actions[gid],
                    reward=rewards[gid],
                    next_state=next_obs[gid]["state_tuple"],
                )

            score += sum(rewards.values())
            obs = next_obs

        summary = env.summary()
        print(f"{episode:>4d} {agent.epsilon:>6.3f}"
              f" {score:>+10.1f}"
              f" {summary['arrived']:>8d}"
              f" {summary['avg_queue_length']:>10.2f}"
              f" {len(agent.Q):>8d}")

        agent.decay_epsilon()

    if output_path is None:
        results_dir = _results_dir()
        os.makedirs(results_dir, exist_ok=True)
        output_path = os.path.join(results_dir, "q_table.json")

    agent.save(output_path)
    print(f"\nQ-table sauvegardee : {output_path}")
    print(f"  {len(agent.Q)} etats visites sur {TOTAL_ETATS} possibles "
          f"({100 * len(agent.Q) / TOTAL_ETATS:.0f}%)")

    return agent


def _results_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "results"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("episodes", nargs="?", type=int, default=30)
    parser.add_argument("--max-time", type=float, default=120.0)
    parser.add_argument("--vehicles", type=int, default=80)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    train(
        nb_episodes=args.episodes,
        max_time=args.max_time,
        target_vehicles=args.vehicles,
        output_path=args.out,
    )


if __name__ == "__main__":
    main()
