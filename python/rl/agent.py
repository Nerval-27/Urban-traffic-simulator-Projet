"""Agent Q-learning pour les feux de circulation."""

import json
import random


# 0 = KEEP, 1 = SWITCH, 2 = EXTEND
NB_ACTIONS = 3


class QLearningAgent:

    def __init__(self, alpha=0.1, gamma=0.9, epsilon=1.0,
                 epsilon_min=0.05, epsilon_decay=0.95):
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay

        # { etat : [Q_KEEP, Q_SWITCH, Q_EXTEND] }
        self.Q = {}
        self.rng = random.Random(0)

    def choose(self, state):
        if self.rng.random() < self.epsilon:
            return self.rng.randrange(NB_ACTIONS)
        return self.greedy_action(state)

    def greedy_action(self, state):
        values = self._q(state)
        best = 0
        for i in range(1, len(values)):
            if values[i] > values[best]:
                best = i
        return best

    def update(self, state, action, reward, next_state):
        current = self._q(state)[action]
        next_max = max(self._q(next_state))
        new_value = current + self.alpha * (reward + self.gamma * next_max - current)
        self._q(state)[action] = new_value

    def decay_epsilon(self):
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def _q(self, state):
        if state not in self.Q:
            self.Q[state] = [0.0] * NB_ACTIONS
        return self.Q[state]

    def save(self, path):
        # Les tuples ne sont pas serialisables en JSON, on les passe en string
        q_str = {}
        for state, values in self.Q.items():
            q_str[",".join(str(x) for x in state)] = values

        with open(path, "w") as f:
            json.dump({
                "alpha":   self.alpha,
                "gamma":   self.gamma,
                "epsilon": self.epsilon,
                "Q":       q_str,
            }, f, indent=2)


def load_agent(path):
    with open(path) as f:
        data = json.load(f)

    agent = QLearningAgent(
        alpha=data["alpha"],
        gamma=data["gamma"],
        epsilon=data["epsilon"],
    )
    for key, values in data["Q"].items():
        state = tuple(int(x) for x in key.split(","))
        agent.Q[state] = list(values)
    return agent
