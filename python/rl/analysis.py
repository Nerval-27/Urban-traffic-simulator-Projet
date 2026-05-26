"""Mesure des durees de phase + recommandations par carrefour.

Pendant un run RL, on chronometre la duree moyenne du vert observee
pour les phases A et B de chaque carrefour. La comparaison au vert
fixe de 35 s donne une duree recommandee, accompagnee d'une phrase
de verdict en francais ("phase A prolongee de 35 s a 70 s",
"phase B raccourcie...") et du pourcentage de gain mesure sur la
file moyenne du meme carrefour.
"""

# Duree verte de reference du cycle fixe, en secondes simulees.
GREEN_FIXE  = 35
# Duree jaune de reference, gardee stable dans les recommandations.
YELLOW_FIXE = 4


class PhaseTracker:
    """Chronometre les phases observees pendant un run.

    Sur chaque tick on detecte les transitions green / yellow / red ;
    quand une phase se termine, sa duree va dans une liste indexee
    par carrefour et par lettre A ou B.
    """

    def __init__(self):
        """Prepare les compteurs de duree observes sur les phases de feux."""
        self.light_manager = None
        # node_id -> (etat_precedent, instant_de_debut)
        self.previous = {}
        # gid -> phase_letter -> etat -> liste de durees
        self.records = {}
        self.sim_time = 0.0

    def reset(self, light_manager):
        """Repart de zero avant une nouvelle simulation de benchmark."""
        self.light_manager = light_manager
        self.previous = {}
        self.records  = {}
        self.sim_time = 0.0

    def tick(self, dt):
        """Avance le suivi des durees de phase pendant la simulation."""
        self.sim_time += dt
        for light in self.light_manager.get_all_lights():
            current = light.state.value
            prev = self.previous.get(light.node_id)
            if prev is None:
                self.previous[light.node_id] = (current, self.sim_time)
                continue

            prev_state, started_at = prev
            if prev_state != current:
                duration = self.sim_time - started_at
                self._add_record(light, prev_state, duration)
                self.previous[light.node_id] = (current, self.sim_time)

    def _add_record(self, light, state, duration):
        """Enregistre une duree observee pour un feu et une couleur."""
        if light.group_id is None or duration < 0.1:
            return
        gid = light.group_id
        phase = light.group_phase

        if gid not in self.records:
            self.records[gid] = {}
        if phase not in self.records[gid]:
            self.records[gid][phase] = {}
        if state not in self.records[gid][phase]:
            self.records[gid][phase][state] = []
        self.records[gid][phase][state].append(duration)

    def stats(self):
        """Construit les statistiques de duree par feu et par phase."""
        out = {}
        for gid, phases in self.records.items():
            entry = {}
            for phase_letter in ("A", "B"):
                phase_data = phases.get(phase_letter, {})
                entry[phase_letter] = {
                    s: _stats(durations)
                    for s, durations in phase_data.items()
                }
            out[gid] = entry
        return out


def _stats(durations):
    """Calcule minimum, moyenne et maximum sur une liste de durees."""
    if not durations:
        return {"n": 0, "avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "n":   len(durations),
        "avg": round(sum(durations) / len(durations), 2),
        "min": round(min(durations), 2),
        "max": round(max(durations), 2),
    }


def recommend(rl_phase_stats, baseline_per_light, rl_per_light, light_to_group):
    """Construit la recommandation de cycle pour chaque carrefour.

    Pour chaque carrefour, on prend la duree moyenne de vert observee
    par l'agent sur chaque phase, on la compare au 35 s fixe de la
    baseline, et on ecrit une phrase de verdict + le gain mesure sur
    la file moyenne.
    """
    queues_baseline = _queues_per_group(baseline_per_light, light_to_group)
    queues_rl       = _queues_per_group(rl_per_light, light_to_group)

    recs = {}
    for gid in sorted(rl_phase_stats.keys()):
        a_green = rl_phase_stats[gid].get("A", {}).get("green", {})
        b_green = rl_phase_stats[gid].get("B", {}).get("green", {})

        rec_a = int(round(a_green["avg"])) if a_green.get("n") else None
        rec_b = int(round(b_green["avg"])) if b_green.get("n") else None

        entry = {
            "current_fixed": {"green_A": GREEN_FIXE, "yellow_A": YELLOW_FIXE,
                               "green_B": GREEN_FIXE, "yellow_B": YELLOW_FIXE},
            "rl_observed": {
                "green_A_avg": a_green.get("avg"), "green_A_n": a_green.get("n"),
                "green_B_avg": b_green.get("avg"), "green_B_n": b_green.get("n"),
            },
            "recommended": _cycle_propose(rec_a, rec_b),
            "verdict":     _verdict(rec_a, rec_b),
        }

        if gid in queues_baseline and gid in queues_rl:
            b_q = queues_baseline[gid]
            r_q = queues_rl[gid]
            improvement = 0.0 if b_q == 0 else (b_q - r_q) / b_q * 100
            entry["performance"] = {
                "avg_queue_baseline": round(b_q, 2),
                "avg_queue_rl":       round(r_q, 2),
                "improvement_pct":    round(improvement, 1),
            }
        recs[f"carrefour_{gid}"] = entry
    return recs


def _queues_per_group(per_light_data, light_to_group):
    """Regroupe les longueurs de file par carrefour controle."""
    by_group = {}
    for light_id, gid in light_to_group.items():
        if light_id not in per_light_data:
            continue
        if gid not in by_group:
            by_group[gid] = []
        by_group[gid].append(
            per_light_data[light_id].get("avg_queue_length", 0.0)
        )
    return {gid: sum(v) / len(v) for gid, v in by_group.items() if v}


def _cycle_propose(green_a, green_b):
    # Le rouge d'une phase = duree de l'autre verte + jaune
    """Transforme les durees apprises en cycle vert jaune rouge propose."""
    g_a = green_a if green_a is not None else GREEN_FIXE
    g_b = green_b if green_b is not None else GREEN_FIXE
    return {
        "green_A":  max(8, g_a),
        "yellow_A": YELLOW_FIXE,
        "red_A":    max(8, g_b) + YELLOW_FIXE,
        "green_B":  max(8, g_b),
        "yellow_B": YELLOW_FIXE,
    }


def _verdict(green_a, green_b):
    """Donne une phrase courte sur l equilibre des deux phases."""
    if green_a is None and green_b is None:
        return "Pas de donnees"
    parts = []
    for label, observed in (("A", green_a), ("B", green_b)):
        if observed is None:
            continue
        delta = observed - GREEN_FIXE
        if abs(delta) <= 2:
            parts.append(f"phase {label} ~= baseline ({observed}s)")
        elif delta < 0:
            parts.append(f"phase {label} raccourcie de {-delta}s "
                         f"(baseline {GREEN_FIXE}s -> {observed}s)")
        else:
            parts.append(f"phase {label} prolongee de {delta}s "
                         f"(baseline {GREEN_FIXE}s -> {observed}s)")
    return "RL recommande : " + " ; ".join(parts)


def _by_improvement(row):
    """Cle de tri qui met les meilleures ameliorations en premier."""
    return -row["improvement"]


def _by_baseline(row):
    """Cle de tri qui met les carrefours les plus charges en premier."""
    return -row["baseline"]


def rank(recommendations, top_n=10):
    """Classe les carrefours en deux palmares de taille top_n.

    top_improved : les carrefours qui beneficient le plus du RL.
    top_problematic : ceux qui ont la file baseline la plus longue,
    donc ceux qui meritent l'attention en priorite.
    """
    rows = []
    for key, entry in recommendations.items():
        if "performance" not in entry:
            continue
        rows.append({
            "carrefour":   key,
            "baseline":    entry["performance"]["avg_queue_baseline"],
            "rl":          entry["performance"]["avg_queue_rl"],
            "improvement": entry["performance"]["improvement_pct"],
        })
    return {
        "top_improved":    sorted(rows, key=_by_improvement)[:top_n],
        "top_problematic": sorted(rows, key=_by_baseline)[:top_n],
        "total_analyzed":  len(rows),
    }


def print_ranking(ranking):
    """Affiche les classements utiles a lire apres le benchmark."""
    def print_section(title, rows):
        """Affiche un bloc de classement avec les files baseline et RL."""
        print("\n" + "=" * 78)
        print(title)
        print("-" * 78)
        print(f"{'Carrefour':<22} {'File baseline':>14} {'File RL':>10} {'Variation':>14}")
        for row in rows:
            print(f"{row['carrefour']:<22}"
                  f"{row['baseline']:>14.2f}"
                  f"{row['rl']:>10.2f}"
                  f"{row['improvement']:>13.1f}%")

    print_section(f"TOP {len(ranking['top_improved'])} CARREFOURS LES PLUS AMELIORES PAR RL",
                  ranking["top_improved"])
    print_section(f"TOP {len(ranking['top_problematic'])} CARREFOURS LES PLUS PROBLEMATIQUES "
                  "(file baseline)",
                  ranking["top_problematic"])
    print("=" * 78)
