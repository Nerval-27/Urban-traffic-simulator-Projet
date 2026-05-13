"""Tests basiques sur les modules RL."""

import os
import tempfile
import unittest

from rl.agent import QLearningAgent, NB_ACTIONS, load_agent
from rl.env import (
    ACTION_KEEP, ACTION_SWITCH, ACTION_EXTEND,
    NB_ACTIONS as ENV_NB_ACTIONS,
    LONG_WAIT, default_map_path,
)
from rl.train import episode_seed


class TestQLearningAgent(unittest.TestCase):

    def test_creation_par_defaut(self):
        agent = QLearningAgent()
        self.assertAlmostEqual(agent.alpha, 0.1)
        self.assertAlmostEqual(agent.gamma, 0.9)
        self.assertAlmostEqual(agent.epsilon, 1.0)
        self.assertEqual(len(agent.Q), 0)

    def test_choose_retourne_action_valide(self):
        agent = QLearningAgent(epsilon=1.0)   # 100% exploration
        for _ in range(30):
            action = agent.choose((0, 0, 0, 0))
            self.assertIn(action, (ACTION_KEEP, ACTION_SWITCH, ACTION_EXTEND))

    def test_greedy_action_choisit_meilleur(self):
        agent = QLearningAgent()
        agent.Q[(1, 2, 3, 1)] = [0.5, 1.5, 0.0]   # action 1 (SWITCH) meilleure
        self.assertEqual(agent.greedy_action((1, 2, 3, 1)), 1)

        agent.Q[(0, 0, 0, 0)] = [2.0, 0.5, 0.0]   # action 0 (KEEP) meilleure
        self.assertEqual(agent.greedy_action((0, 0, 0, 0)), 0)

        agent.Q[(2, 2, 1, 0)] = [0.0, 0.5, 3.0]   # action 2 (EXTEND) meilleure
        self.assertEqual(agent.greedy_action((2, 2, 1, 0)), 2)

    def test_update_modifie_q_value(self):
        agent = QLearningAgent(alpha=0.5, gamma=0.0)
        # Avec gamma=0, Q(s,a) = (1-alpha)*Q(s,a) + alpha*reward
        # Reward=10, alpha=0.5 -> Q passe de 0 à 5
        agent.update(state=(0, 0, 0, 0), action=0,
                     reward=10.0, next_state=(0, 0, 0, 0))
        self.assertAlmostEqual(agent.Q[(0, 0, 0, 0)][0], 5.0)

    def test_decay_epsilon_diminue(self):
        agent = QLearningAgent(epsilon=1.0, epsilon_decay=0.5, epsilon_min=0.05)
        agent.decay_epsilon()
        self.assertAlmostEqual(agent.epsilon, 0.5)
        agent.decay_epsilon()
        self.assertAlmostEqual(agent.epsilon, 0.25)

    def test_decay_ne_passe_pas_sous_min(self):
        agent = QLearningAgent(epsilon=0.05, epsilon_decay=0.5, epsilon_min=0.05)
        agent.decay_epsilon()
        self.assertAlmostEqual(agent.epsilon, 0.05)

    def test_save_et_load_round_trip(self):
        agent = QLearningAgent(alpha=0.2, gamma=0.85, epsilon=0.42)
        agent.Q[(1, 2, 3, 1)] = [0.5, 1.5, 0.8]
        agent.Q[(0, 0, 0, 0)] = [-2.0, 3.0, 1.0]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            agent.save(path)
            recharge = load_agent(path)

            self.assertAlmostEqual(recharge.alpha, 0.2)
            self.assertAlmostEqual(recharge.gamma, 0.85)
            self.assertAlmostEqual(recharge.epsilon, 0.42)
            self.assertEqual(len(recharge.Q), 2)
            self.assertEqual(recharge.Q[(1, 2, 3, 1)], [0.5, 1.5, 0.8])
            self.assertEqual(recharge.Q[(0, 0, 0, 0)], [-2.0, 3.0, 1.0])
        finally:
            os.unlink(path)


class TestRLEnv(unittest.TestCase):
    """Tests rapides sur l'environnement (chargement complet du réseau)."""

    @classmethod
    def setUpClass(cls):
        from rl.env import TrafficRLEnv
        cls.env = TrafficRLEnv(
            map_path=default_map_path(),
            step_dt=5.0,
            max_time=10.0,   # très court
            target_vehicles=20,
        )

    def test_reset_retourne_observations(self):
        obs = self.env.reset()
        self.assertGreater(len(obs), 0)

    def test_observation_a_bonnes_cles(self):
        obs = self.env.reset()
        sample = next(iter(obs.values()))
        attendu = {
            "queue_A", "queue_B", "approach_A", "approach_B",
            "arrival_A", "arrival_B", "service_A", "service_B",
            "saturation_A", "saturation_B", "pressure_A", "pressure_B",
            "oldest_wait_A", "oldest_wait_B", "phase", "state", "stage",
            "time_in_phase", "time_remaining", "waiting_long",
            "switch_requested", "state_tuple",
        }
        self.assertEqual(set(sample.keys()), attendu)

    def test_state_tuple_est_4uplet_entiers(self):
        obs = self.env.reset()
        sample = next(iter(obs.values()))
        st = sample["state_tuple"]
        self.assertEqual(len(st), 8)
        for v in st:
            self.assertIsInstance(v, int)

    def test_step_avance_le_temps(self):
        self.env.reset()
        actions = {gid: ACTION_KEEP for gid in self.env.group_ids()}
        _obs, _r, _done, info = self.env.step(actions)
        self.assertGreater(info["sim_time"], 0)

    def test_constantes_actions(self):
        self.assertEqual(ACTION_KEEP, 0)
        self.assertEqual(ACTION_SWITCH, 1)
        self.assertEqual(ACTION_EXTEND, 2)
        self.assertEqual(NB_ACTIONS, 3)
        self.assertEqual(ENV_NB_ACTIONS, 3)

    def test_long_wait_constant(self):
        self.assertEqual(LONG_WAIT, 30.0)

    def test_seed_change_a_chaque_episode(self):
        self.assertEqual(episode_seed(42, 1), 42)
        self.assertEqual(episode_seed(42, 2), 43)
        self.assertEqual(episode_seed(100, 5), 104)

    def test_penalite_plus_forte_si_file_explose(self):
        self.env.reset()
        obs = {
            "queue_A": 4,
            "queue_B": 0,
            "pressure_A": 0.0,
            "pressure_B": 0.0,
        }
        before = {"carrefour_test": {"queue": 0, "pressure": 0.0}}

        penalty = self.env._worsening_penalty(
            "carrefour_test",
            obs,
            before,
        )

        self.assertGreater(penalty, 4 * 1.5)

    def test_phases_conflictuelles_jamais_vertes_ensemble(self):
        self.env.reset()

        for _ in range(120):
            for gid in self.env.group_ids()[::9]:
                self.env.light_manager.request_phase_switch(gid)
            self.env.light_manager.update(0.5)
            self._assert_no_conflicting_green()

    def test_extension_garde_les_phases_synchronisees(self):
        self.env.reset()

        for _ in range(80):
            for gid in self.env.group_ids()[::11]:
                self.env.light_manager.extend_green(gid, 5.0)
            self.env.light_manager.update(0.5)
            self._assert_no_conflicting_green()

    def _assert_no_conflicting_green(self):
        manager = self.env.light_manager
        for gid in self.env.group_ids():
            lights_A = manager.get_group_lights(gid, "A")
            lights_B = manager.get_group_lights(gid, "B")
            if not lights_A or not lights_B:
                continue

            green_A = any(light.is_green() for light in lights_A)
            green_B = any(light.is_green() for light in lights_B)
            self.assertFalse(
                green_A and green_B,
                f"Phases A et B vertes ensemble au carrefour {gid}",
            )


if __name__ == "__main__":
    unittest.main()
