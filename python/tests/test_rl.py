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


class TestQLearningAgent(unittest.TestCase):

    def test_creation_par_defaut(self):
        agent = QLearningAgent()
        self.assertAlmostEqual(agent.alpha, 0.1)
        self.assertAlmostEqual(agent.gamma, 0.9)
        self.assertAlmostEqual(agent.epsilon, 1.0)
        self.assertEqual(len(agent.Q), 0)

    def test_choose_retourne_action_valide(self):
        agent = QLearningAgent(epsilon=1.0)
        for _ in range(30):
            action = agent.choose((0, 0, 0, 0))
            self.assertIn(action, (ACTION_KEEP, ACTION_SWITCH, ACTION_EXTEND))

    def test_greedy_action_choisit_meilleur(self):
        agent = QLearningAgent()
        agent.Q[(1, 2, 3, 1)] = [0.5, 1.5, 0.0]
        self.assertEqual(agent.greedy_action((1, 2, 3, 1)), 1)

        agent.Q[(0, 0, 0, 0)] = [2.0, 0.5, 0.0]
        self.assertEqual(agent.greedy_action((0, 0, 0, 0)), 0)

        agent.Q[(2, 2, 1, 0)] = [0.0, 0.5, 3.0]
        self.assertEqual(agent.greedy_action((2, 2, 1, 0)), 2)

    def test_update_modifie_q_value(self):
        agent = QLearningAgent(alpha=0.5, gamma=0.0)
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

    @classmethod
    def setUpClass(cls):
        from rl.env import TrafficRLEnv
        cls.env = TrafficRLEnv(
            map_path=default_map_path(),
            step_dt=5.0,
            max_time=10.0,
            target_vehicles=20,
        )

    def test_reset_retourne_observations(self):
        obs = self.env.reset()
        self.assertGreater(len(obs), 0)

    def test_observation_a_bonnes_cles(self):
        obs = self.env.reset()
        sample = next(iter(obs.values()))
        attendu = {"queue_A", "queue_B", "phase", "state",
                   "time_in_phase", "waiting_long", "state_tuple"}
        self.assertEqual(set(sample.keys()), attendu)

    def test_state_tuple_est_4uplet_entiers(self):
        obs = self.env.reset()
        sample = next(iter(obs.values()))
        st = sample["state_tuple"]
        self.assertEqual(len(st), 4)
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


class TestBenchmarkVerdict(unittest.TestCase):
    """Verifie que le verdict est nuance et pas trompeur."""

    def setUp(self):
        from rl.benchmark import _build_verdict
        self.build = _build_verdict

    def _row(self, improvement, target, passed):
        return {"improvement": improvement, "target": target, "passed": passed}

    def test_succes_global_quand_tout_passe(self):
        rows = [
            self._row(0.20, 0.15, True),
            self._row(0.30, 0.20, True),
            self._row(0.40, 0.10, True),
        ]
        v = self.build(rows)
        self.assertEqual(v["verdict"], "SUCCES GLOBAL")
        self.assertEqual(v["passed"], 3)
        self.assertTrue(v["all_pass"])

    def test_succes_majoritaire_si_2_sur_3_passent_et_tout_progresse(self):
        rows = [
            self._row(0.10, 0.15, False),  # FAIL mais positif
            self._row(0.30, 0.20, True),
            self._row(0.40, 0.10, True),
        ]
        v = self.build(rows)
        self.assertEqual(v["verdict"], "SUCCES MAJORITAIRE")
        self.assertEqual(v["passed"], 2)

    def test_progres_partiel_si_1_sur_3_et_tout_progresse(self):
        rows = [
            self._row(0.05, 0.15, False),
            self._row(0.10, 0.20, False),
            self._row(0.40, 0.10, True),
        ]
        v = self.build(rows)
        self.assertEqual(v["verdict"], "PROGRES PARTIEL")
        self.assertEqual(v["passed"], 1)

    def test_progres_detecte_si_aucune_cible_mais_tout_dans_le_bon_sens(self):
        rows = [
            self._row(0.05, 0.15, False),
            self._row(0.10, 0.20, False),
            self._row(0.05, 0.10, False),
        ]
        v = self.build(rows)
        self.assertEqual(v["verdict"], "PROGRES DETECTE (sous cible)")

    def test_echec_si_une_metrique_regresse(self):
        rows = [
            self._row(0.30, 0.15, True),
            self._row(-0.05, 0.20, False),  # regression !
            self._row(0.40, 0.10, True),
        ]
        v = self.build(rows)
        self.assertEqual(v["verdict"], "ECHEC")


if __name__ == "__main__":
    unittest.main()
