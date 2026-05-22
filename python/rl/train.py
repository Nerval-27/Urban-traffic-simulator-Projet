"""Entrainement de l'agent Q-learning."""

import argparse
import os

from rl.agent import QLearningAgent
from rl.env import TrafficRLEnv, default_map_path


# 4 bins file_A * 4 bins file_B * 5 phases * 3 bins temps
TOTAL_ETATS = 4 * 4 * 5 * 3


def episode_seed(seed_base, episode):
    # Une seed differente par episode pour que l'agent voit des scenarios varies
    return seed_base + episode - 1


def train(nb_episodes=30, max_time=120.0, target_vehicles=80,
          output_path=None, best_output_path=None, seed_base=42):

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
          f"de {max_time:.0f}s simulees.")
    print(f"Seed de depart : {seed_base} (une seed differente par episode).\n")
    print(f"{'ep':>4} {'seed':>6} {'eps':>6} {'reward':>10} {'arrived':>8}"
          f" {'avg_queue':>10} {'states':>8} {'best':>6}")

    best_score = None
    best_episode = 0
    best_q = None

    for episode in range(1, nb_episodes + 1):
        env.random_seed = episode_seed(seed_base, episode)
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

        # Score combine pour choisir le meilleur snapshot
        episode_score = (
            score
            + 20.0 * summary.get("completion_rate", 0.0)
            + 4.0 * summary.get("throughput_per_min", 0.0)
            - 2.0 * summary.get("avg_queue_length", 0.0)
        )

        if best_score is None or episode_score > best_score:
            best_score = episode_score
            best_episode = episode
            best_q = {state: list(values) for state, values in agent.Q.items()}

        print(f"{episode:>4d} {env.random_seed:>6d}"
              f" {agent.epsilon:>6.3f}"
              f" {score:>+10.1f}"
              f" {summary['arrived']:>8d}"
              f" {summary['avg_queue_length']:>10.2f}"
              f" {len(agent.Q):>8d}"
              f" {best_episode:>6d}")

        agent.decay_epsilon()

    if output_path is None:
        results_dir = _results_dir()
        os.makedirs(results_dir, exist_ok=True)
        output_path = os.path.join(results_dir, "q_table.json")
    else:
        results_dir = os.path.dirname(os.path.abspath(output_path))

    if best_output_path is None:
        best_output_path = os.path.join(results_dir, "q_table_best.json")

    agent.save(output_path)
    print(f"\nQ-table finale sauvegardee : {output_path}")
    print(f"  {len(agent.Q)} etats visites sur {TOTAL_ETATS} possibles "
          f"({100 * len(agent.Q) / TOTAL_ETATS:.0f}%)")

    # Sauvegarde la meilleure Q-table rencontree pendant l'entrainement
    if best_q is not None:
        best_agent = QLearningAgent(
            alpha=agent.alpha,
            gamma=agent.gamma,
            epsilon=agent.epsilon,
        )
        best_agent.Q = best_q
        best_agent.save(best_output_path)
        print(f"Meilleure Q-table sauvegardee : {best_output_path}")
        print(f"  (Episode {best_episode}, score={best_score:.1f})")

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
    parser.add_argument("--best-out", type=str, default=None)
    parser.add_argument("--seed-base", type=int, default=42)
    args = parser.parse_args()

    train(
        nb_episodes=args.episodes,
        max_time=args.max_time,
        target_vehicles=args.vehicles,
        output_path=args.out,
        best_output_path=args.best_out,
        seed_base=args.seed_base,
    )


if __name__ == "__main__":
    main()
