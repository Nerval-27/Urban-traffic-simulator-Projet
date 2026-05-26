"""Agent Q-learning pour les feux de circulation.

Une seule classe QLearningAgent fait tout : choix d'action, mise a jour,
sauvegarde JSON. Pas de framework externe, la Q-table est un dictionnaire
Python que tous les carrefours du reseau se partagent.
"""

import json
import random


# 0 = KEEP, 1 = SWITCH, 2 = EXTEND
NB_ACTIONS = 3


class QLearningAgent:
    """Agent Q-learning tabulaire.

    On choisit en epsilon-greedy pendant l'entrainement, en greedy pur
    une fois la Q-table chargee depuis le JSON.
    """

    def __init__(self, alpha=0.1, gamma=0.9, epsilon=1.0,
                 epsilon_min=0.05, epsilon_decay=0.95):
        # alpha = vitesse d'apprentissage, gamma = importance du futur
        self.alpha = alpha
        self.gamma = gamma
        # epsilon decroit a chaque episode : on explore beaucoup au depart,
        # puis on exploite ce qu'on a appris
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay

        # { etat : [Q_KEEP, Q_SWITCH, Q_EXTEND] }
        self.Q = {}
        # Generateur dedie pour que les tests soient reproductibles
        self.rng = random.Random(0)

    def choose(self, state):
        """Action epsilon-greedy : tire au hasard avec proba epsilon,
        sinon prend la meilleure action connue."""
        if self.rng.random() < self.epsilon:
            return self.rng.randrange(NB_ACTIONS)
        return self.greedy_action(state)

    def greedy_action(self, state):
        """Renvoie l'indice de l'action de meilleure Q-valeur.

        En cas d'egalite, on garde la premiere rencontree (donc KEEP par
        defaut, ce qui evite les SWITCH inutiles tant que rien n'est appris).
        """
        values = self._q(state)
        best = 0
        for i in range(1, len(values)):
            if values[i] > values[best]:
                best = i
        return best

    def update(self, state, action, reward, next_state):
        """Mise a jour Q-learning, equation de Bellman :

            Q(s, a) <- Q(s, a) + alpha * (r + gamma * max Q(s', .) - Q(s, a))
        """
        current = self._q(state)[action]
        next_max = max(self._q(next_state))
        new_value = current + self.alpha * (reward + self.gamma * next_max - current)
        self._q(state)[action] = new_value

    def decay_epsilon(self):
        """Reduit epsilon a la fin d'un episode, en restant au-dessus
        du plancher epsilon_min pour ne pas couper l'exploration."""
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def _q(self, state):
        """Vecteur de Q-valeurs pour cet etat, cree a la volee si absent.

        On ne pre-remplit pas les 240 etats : seuls ceux reellement vus
        finissent dans la table.
        """
        if state not in self.Q:
            self.Q[state] = [0.0] * NB_ACTIONS
        return self.Q[state]

    def save(self, path):
        """Sauvegarde la Q-table en JSON.

        Les cles sont des tuples Python, non serialisables en JSON, donc
        on les convertit en chaines "0,1,2,1". load_agent fait l'inverse.
        """
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
    """Recharge un agent depuis un fichier JSON ecrit par save().

    Les cles d'etat sont relues comme des tuples d'entiers, pour
    qu'elles soient utilisables par choose() et update().
    """
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
