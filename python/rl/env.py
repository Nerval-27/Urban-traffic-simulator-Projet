"""Environnement RL autour de la simulation."""

import os
import random

from simulation.graph import RoadGraph
from simulation.loader import load_network
from simulation.lights import LightState, TrafficLightManager
from simulation.metrics import TrafficMetrics
from simulation.vehicle import VehicleManager


ACTION_KEEP   = 0
ACTION_SWITCH = 1
ACTION_EXTEND = 2
NB_ACTIONS    = 3

EXTEND_SECONDS = 5.0
LONG_WAIT      = 30.0

SWITCH_MARGIN = 4.0
EXTEND_MARGIN = 3.0
KEEP_PRESSURE_MARGIN = 8.0

TRAVEL_TIME_WEIGHT = 0.035
STOPPED_RATIO_WEIGHT = 6.0
WORSE_PRESSURE_WEIGHT = 0.35
WORSE_QUEUE_WEIGHT = 1.5
WORSE_QUEUE_SPIKE = 3.0
WORSE_PRESSURE_SPIKE = 12.0
WORSE_SPIKE_PENALTY = 4.0


def default_map_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "data", "map_clean.json"))


def _bin_queue(n):
    if n == 0: return 0
    if n <= 2: return 1
    if n <= 5: return 2
    return 3


def _bin_pressure(value):
    if value <= 0.0: return 0
    if value <= 8.0: return 1
    if value <= 20.0: return 2
    return 3


def _bin_saturation(value):
    if value <= 0.0: return 0
    if value <= 0.8: return 1
    if value <= 1.2: return 2
    return 3


def _bin_time(t):
    if t <= 10.0: return 0
    if t <= 25.0: return 1
    return 2


def _phase_code(phase, state):
    if phase == "A" and state == "green":  return 0
    if phase == "A" and state == "yellow": return 1
    if phase == "B" and state == "green":  return 2
    if phase == "B" and state == "yellow": return 3
    return 4


def _dominant_phase(lights_A, lights_B):
    for light in lights_A:
        if light.state == LightState.GREEN:
            return "A", "green", light.time_in_phase
        if light.state == LightState.YELLOW:
            return "A", "yellow", light.time_in_phase
    for light in lights_B:
        if light.state == LightState.GREEN:
            return "B", "green", light.time_in_phase
        if light.state == LightState.YELLOW:
            return "B", "yellow", light.time_in_phase
    first = lights_A or lights_B
    return "X", "red", first[0].time_in_phase if first else 0.0


def _phase_metrics(lights, light_obs):
    data = {
        "queue": 0,
        "approaching": 0,
        "oldest_wait": 0.0,
        "arrival_rate": 0.0,
        "service_rate": 0.0,
        "saturation": 0.0,
        "pressure": 0.0,
    }

    for light in lights:
        obs = light_obs.get(light.node_id)
        if obs is None:
            continue
        data["queue"] += obs.queue_length
        data["approaching"] += obs.approaching
        data["oldest_wait"] = max(data["oldest_wait"], obs.oldest_wait_s)
        data["arrival_rate"] += obs.arrival_rate
        data["service_rate"] += obs.service_rate
        data["pressure"] += obs.pressure

    if data["arrival_rate"] <= 0.0:
        data["saturation"] = 0.0
    elif data["service_rate"] <= 1e-9:
        data["saturation"] = 9.99
    else:
        data["saturation"] = min(9.99, data["arrival_rate"] / data["service_rate"])

    return data


def observe(light_manager, metrics, group_ids):
    observations = {}
    if metrics.latest_observation is None:
        return observations

    light_obs = metrics.latest_observation.lights

    for gid in group_ids:
        lights_A = light_manager.get_group_lights(gid, "A")
        lights_B = light_manager.get_group_lights(gid, "B")

        queue_A = sum(light_obs[l.node_id].queue_length
                      for l in lights_A if l.node_id in light_obs)
        queue_B = sum(light_obs[l.node_id].queue_length
                      for l in lights_B if l.node_id in light_obs)
        metrics_A = _phase_metrics(lights_A, light_obs)
        metrics_B = _phase_metrics(lights_B, light_obs)
        waiting_long = sum(
            1 for l in (lights_A + lights_B)
            if l.node_id in light_obs
            and light_obs[l.node_id].oldest_wait_s > LONG_WAIT
        )

        status = light_manager.get_group_status(gid)
        if status is None:
            phase, state, time_in_phase = _dominant_phase(lights_A, lights_B)
            stage = state
            time_remaining = 0.0
            switch_requested = False
        else:
            phase = status["phase"]
            state = status["state"]
            stage = status["stage"]
            time_in_phase = status["time_in_phase"]
            time_remaining = status["time_remaining"]
            switch_requested = status["switch_requested"]

        observations[gid] = {
            "queue_A":       queue_A,
            "queue_B":       queue_B,
            "approach_A":     metrics_A["approaching"],
            "approach_B":     metrics_B["approaching"],
            "arrival_A":      metrics_A["arrival_rate"],
            "arrival_B":      metrics_B["arrival_rate"],
            "service_A":      metrics_A["service_rate"],
            "service_B":      metrics_B["service_rate"],
            "saturation_A":   metrics_A["saturation"],
            "saturation_B":   metrics_B["saturation"],
            "pressure_A":     metrics_A["pressure"],
            "pressure_B":     metrics_B["pressure"],
            "oldest_wait_A":  metrics_A["oldest_wait"],
            "oldest_wait_B":  metrics_B["oldest_wait"],
            "phase":         phase,
            "state":         state,
            "stage":         stage,
            "time_in_phase": time_in_phase,
            "time_remaining": time_remaining,
            "waiting_long":  waiting_long,
            "switch_requested": switch_requested,
            "state_tuple": (
                _bin_queue(queue_A),
                _bin_queue(queue_B),
                _bin_saturation(metrics_A["saturation"]),
                _bin_saturation(metrics_B["saturation"]),
                _bin_pressure(metrics_A["pressure"]),
                _bin_pressure(metrics_B["pressure"]),
                _phase_code(phase, state),
                _bin_time(time_in_phase),
            ),
        }
    return observations


class TrafficRLEnv:

    def __init__(self, map_path, step_dt=5.0, sub_dt=0.1, max_time=300.0,
                 initial_vehicles=15, target_vehicles=100, max_vehicles=150,
                 spawn_interval=3.0, random_seed=42):
        self.map_path         = map_path
        self.step_dt          = step_dt
        self.sub_dt           = sub_dt
        self.max_time         = max_time
        self.initial_vehicles = initial_vehicles
        self.target_vehicles  = target_vehicles
        self.max_vehicles     = max_vehicles
        self.spawn_interval   = spawn_interval
        self.random_seed      = random_seed

        # Le reseau OSM est lourd a parser, on le charge une fois
        self._network = load_network(map_path)

        self.graph           = None
        self.light_manager   = None
        self.vehicle_manager = None
        self.metrics         = None
        self.sim_time        = 0.0

        self._spawn_timer         = 0.0
        self._arrived_before_step = 0
        self._group_ids           = []

    def reset(self):
        self.graph = RoadGraph()
        self.graph.build_from_network(self._network)

        self.light_manager = TrafficLightManager()
        self.light_manager.build_from_graph(self.graph)

        self.vehicle_manager = VehicleManager(
            self.graph, self.light_manager,
            rng=random.Random(self.random_seed),
        )
        self.vehicle_manager.build_edge_index()
        self.vehicle_manager.spawn_batch(self.initial_vehicles)

        self.metrics = TrafficMetrics(sample_interval=1.0)
        self.metrics.update(self.sub_dt, self.vehicle_manager, self.light_manager)

        self.sim_time             = 0.0
        self._spawn_timer         = 0.0
        self._arrived_before_step = 0
        self._group_ids           = sorted(self.light_manager.get_groups().keys())

        return observe(self.light_manager, self.metrics, self._group_ids)

    def step(self, actions, on_tick=None):
        if self.light_manager is None:
            raise RuntimeError("env.reset() doit etre appele avant step().")

        before = observe(self.light_manager, self.metrics, self._group_ids)
        before_loads = self._group_loads(before)

        for gid, action in actions.items():
            if action == ACTION_SWITCH:
                self.light_manager.request_phase_switch(gid)
            elif action == ACTION_EXTEND:
                self.light_manager.extend_green(gid, EXTEND_SECONDS)

        self._arrived_before_step = self.vehicle_manager.total_arrived

        nb_subticks = max(1, int(round(self.step_dt / self.sub_dt)))
        for _ in range(nb_subticks):
            self.light_manager.update(self.sub_dt)
            self.vehicle_manager.update(self.sub_dt)
            self.metrics.update(self.sub_dt, self.vehicle_manager, self.light_manager)
            if on_tick is not None:
                on_tick(self.sub_dt)
            self.sim_time     += self.sub_dt
            self._spawn_timer += self.sub_dt
            self._spawn_more()

        observations = observe(self.light_manager, self.metrics, self._group_ids)
        rewards = self._rewards(observations, actions, before_loads)
        done    = self.sim_time >= self.max_time
        info = {
            "sim_time":      self.sim_time,
            "total_arrived": self.vehicle_manager.total_arrived,
            "total_active":  self.vehicle_manager.get_active_count(),
        }
        return observations, rewards, done, info

    def group_ids(self):
        return list(self._group_ids)

    def summary(self):
        return self.metrics.summary() if self.metrics else {}

    def _spawn_more(self):
        if self._spawn_timer < self.spawn_interval:
            return
        self._spawn_timer = 0.0
        active = self.vehicle_manager.get_active_count()
        budget = min(self.target_vehicles - active,
                     self.max_vehicles - active,
                     10)
        if budget > 0:
            self.vehicle_manager.spawn_batch(budget)

    def _rewards(self, observations, actions, before_loads):
        arrived = self.vehicle_manager.total_arrived - self._arrived_before_step
        bonus = 0.3 * arrived
        travel_penalty = self._travel_time_penalty()

        rewards = {}
        for gid, obs in observations.items():
            if obs["phase"] == "A" and obs["state"] == "green":
                red_pressure = obs["pressure_B"]
                green_pressure = obs["pressure_A"]
                red_wait = obs["oldest_wait_B"]
                red_saturation = obs["saturation_B"]
            elif obs["phase"] == "B" and obs["state"] == "green":
                red_pressure = obs["pressure_A"]
                green_pressure = obs["pressure_B"]
                red_wait = obs["oldest_wait_A"]
                red_saturation = obs["saturation_A"]
            else:
                red_pressure = obs["pressure_A"] + obs["pressure_B"]
                green_pressure = 0.0
                red_wait = max(obs["oldest_wait_A"], obs["oldest_wait_B"])
                red_saturation = max(obs["saturation_A"], obs["saturation_B"])

            action = actions.get(gid, ACTION_KEEP)
            action_penalty = self._action_penalty(action, obs, red_pressure, green_pressure)
            worsening_penalty = self._worsening_penalty(gid, obs, before_loads)

            penalty = (
                red_pressure
                + 0.25 * green_pressure
                + 0.06 * red_wait
                + 1.2 * red_saturation
                + 1.5 * obs["waiting_long"]
                + action_penalty
                + worsening_penalty
                + travel_penalty
            )
            rewards[gid] = -penalty + bonus
        return rewards

    def _group_loads(self, observations):
        loads = {}
        for gid, obs in observations.items():
            loads[gid] = {
                "queue": obs["queue_A"] + obs["queue_B"],
                "pressure": obs["pressure_A"] + obs["pressure_B"],
            }
        return loads

    def _worsening_penalty(self, gid, obs, before_loads):
        before = before_loads.get(gid)
        if before is None:
            return 0.0

        queue_now = obs["queue_A"] + obs["queue_B"]
        pressure_now = obs["pressure_A"] + obs["pressure_B"]

        queue_delta = max(0.0, queue_now - before["queue"])
        pressure_delta = max(0.0, pressure_now - before["pressure"])
        spike_penalty = 0.0

        if queue_delta >= WORSE_QUEUE_SPIKE:
            spike_penalty += WORSE_SPIKE_PENALTY
        if pressure_delta >= WORSE_PRESSURE_SPIKE:
            spike_penalty += WORSE_SPIKE_PENALTY

        return (
            queue_delta * WORSE_QUEUE_WEIGHT
            + pressure_delta * WORSE_PRESSURE_WEIGHT
            + spike_penalty
        )

    def _travel_time_penalty(self):
        vehicles = self.vehicle_manager.get_vehicle_list()
        if not vehicles:
            return 0.0

        avg_travel_time = sum(v.travel_time for v in vehicles) / len(vehicles)
        stopped = sum(1 for v in vehicles if getattr(v.state, "name", "") == "STOPPED")
        stopped_ratio = stopped / len(vehicles)

        return (
            avg_travel_time * TRAVEL_TIME_WEIGHT
            + stopped_ratio * STOPPED_RATIO_WEIGHT
        )

    def _action_penalty(self, action, obs, red_pressure, green_pressure):
        if action == ACTION_KEEP:
            if (
                obs["state"] == "green"
                and red_pressure > green_pressure + KEEP_PRESSURE_MARGIN
                and obs["time_in_phase"] > 18.0
            ):
                return 2.0
            return 0.0

        if obs["stage"] != "green":
            return 2.5

        if action == ACTION_SWITCH and red_pressure <= green_pressure + SWITCH_MARGIN:
            return 1.5

        if action == ACTION_EXTEND and green_pressure <= red_pressure + EXTEND_MARGIN:
            return 1.0

        return 0.0


class RLController:
    """Branche un agent entraine sur la simulation Pygame."""

    def __init__(self, agent, light_manager, metrics, step_dt=5.0):
        self.agent         = agent
        self.light_manager = light_manager
        self.metrics       = metrics
        self.step_dt       = step_dt

        self._timer       = 0.0
        self._sim_time    = 0.0
        self._group_ids   = sorted(light_manager.get_groups().keys())

        self.last_actions       = {}
        self.action_count       = {ACTION_KEEP: 0, ACTION_SWITCH: 0, ACTION_EXTEND: 0}
        self.recent_switches    = {}
        self.last_decision_time = 0.0

    def tick(self, dt):
        self._sim_time += dt
        self._timer    += dt
        if self._timer < self.step_dt:
            return
        self._timer = 0.0
        self.last_decision_time = self._sim_time

        observations = observe(self.light_manager, self.metrics, self._group_ids)
        actions = {}
        for gid, obs in observations.items():
            action = self.agent.greedy_action(obs["state_tuple"])
            actions[gid] = action
            self.action_count[action] += 1
            if action == ACTION_SWITCH:
                if self.light_manager.request_phase_switch(gid):
                    self.recent_switches[gid] = self._sim_time
            elif action == ACTION_EXTEND:
                self.light_manager.extend_green(gid, EXTEND_SECONDS)
        self.last_actions = actions

    def time_since_switch(self, gid):
        ts = self.recent_switches.get(gid)
        return None if ts is None else self._sim_time - ts

    def stats(self):
        total = sum(self.action_count.values()) or 1
        return {
            "groups":         len(self._group_ids),
            "step_dt":        self.step_dt,
            "keep_count":     self.action_count[ACTION_KEEP],
            "switch_count":   self.action_count[ACTION_SWITCH],
            "extend_count":   self.action_count[ACTION_EXTEND],
            "switch_ratio":   self.action_count[ACTION_SWITCH] / total,
            "qtable_size":    len(self.agent.Q),
            "since_decision": self._sim_time - self.last_decision_time,
        }
