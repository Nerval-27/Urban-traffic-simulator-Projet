"""Mesures de circulation pour comparer les stratégies de feux."""

import csv
import json
import math
from dataclasses import dataclass
from statistics import mean, median
from typing import Dict, List, Optional, Tuple


APPROACH_RADIUS_M = 80.0

QUEUE_WEIGHT = 2.0
APPROACH_WEIGHT = 0.5
WAIT_WEIGHT = 0.1


@dataclass
class LightObservation:
    light_id: int
    state: Optional[str]
    time_remaining: float
    queue_length: int
    approaching: int
    waiting: int
    oldest_wait_s: float
    avg_wait_s: float
    stop_events: int
    max_queue_length: int
    pressure: float
    green_ratio: float
    yellow_ratio: float
    red_ratio: float
    group_id: Optional[int] = None
    group_phase: Optional[str] = None
    controlled_from_nodes: Optional[List[int]] = None

    def to_dict(self) -> dict:
        return {
            "light_id": self.light_id,
            "state": self.state,
            "time_remaining": round(self.time_remaining, 3),
            "queue_length": self.queue_length,
            "approaching": self.approaching,
            "waiting": self.waiting,
            "oldest_wait_s": round(self.oldest_wait_s, 3),
            "avg_wait_s": round(self.avg_wait_s, 3),
            "stop_events": self.stop_events,
            "max_queue_length": self.max_queue_length,
            "pressure": round(self.pressure, 3),
            "green_ratio": round(self.green_ratio, 3),
            "yellow_ratio": round(self.yellow_ratio, 3),
            "red_ratio": round(self.red_ratio, 3),
            "group_id": self.group_id,
            "group_phase": self.group_phase,
            "controlled_from_nodes": self.controlled_from_nodes or [],
        }


@dataclass
class TrafficObservation:
    time: float
    active: int
    spawned: int
    arrived: int
    moving: int
    stopped: int
    braking: int
    queued: int
    max_queue: int
    lights: Dict[int, LightObservation]

    def to_dict(self) -> dict:
        return {
            "time": round(self.time, 3),
            "active": self.active,
            "spawned": self.spawned,
            "arrived": self.arrived,
            "moving": self.moving,
            "stopped": self.stopped,
            "braking": self.braking,
            "queued": self.queued,
            "max_queue": self.max_queue,
            "lights": {
                str(light_id): obs.to_dict()
                for light_id, obs in self.lights.items()
            },
        }


@dataclass
class MetricSnapshot:
    time: float
    active: int
    spawned: int
    arrived: int
    moving: int
    stopped: int
    braking: int
    queued: int
    max_queue: int
    throughput_per_min: float
    avg_queue_length: float
    avg_waiting_at_lights: float
    avg_speed_m_s: float
    congestion_ratio: float

    def to_dict(self) -> dict:
        return {
            "time": round(self.time, 3),
            "active": self.active,
            "spawned": self.spawned,
            "arrived": self.arrived,
            "moving": self.moving,
            "stopped": self.stopped,
            "braking": self.braking,
            "queued": self.queued,
            "max_queue": self.max_queue,
            "throughput_per_min": round(self.throughput_per_min, 3),
            "avg_queue_length": round(self.avg_queue_length, 3),
            "avg_waiting_at_lights": round(self.avg_waiting_at_lights, 3),
            "avg_speed_m_s": round(self.avg_speed_m_s, 3),
            "congestion_ratio": round(self.congestion_ratio, 3),
        }


class TrafficMetrics:
    def __init__(self, sample_interval: float = 1.0,
                 approach_radius_m: float = APPROACH_RADIUS_M):
        self.sample_interval = sample_interval
        self.approach_radius_m = approach_radius_m

        self.elapsed = 0.0
        self._sample_timer = 0.0
        self._started = False

        self.snapshots: List[MetricSnapshot] = []
        self.latest_observation: Optional[TrafficObservation] = None
        self.latest_stats: Dict[str, int] = {}

        self.active_vehicle_time = 0.0
        self.queue_vehicle_time = 0.0
        self.light_wait_vehicle_time = 0.0
        self.stopped_vehicle_time = 0.0
        self.distance_sum = 0.0

        self.max_queue = 0
        self.max_waiting_at_light = 0

        self.trip_times: List[float] = []
        self.completed_light_waits: List[float] = []

        self.queue_time_by_light: Dict[int, float] = {}
        self.max_queue_by_light: Dict[int, int] = {}
        self.state_time_by_light: Dict[int, Dict[str, float]] = {}
        self.completed_waits_by_light: Dict[int, List[float]] = {}
        self.last_light_stop_events: Dict[int, int] = {}

        self._current_light_waits: Dict[Tuple[int, int], float] = {}
        self._last_seen_travel_time: Dict[int, float] = {}
        self._recorded_vehicle_ids: set = set()
        self._recorded_arrivals = 0

    def update(self, dt: float, vehicle_manager, light_manager) -> TrafficObservation:
        if dt <= 0.0:
            return self.latest_observation or self._empty_observation()

        stats = vehicle_manager.get_stats()
        vehicles = vehicle_manager.get_vehicle_list()
        queue_lengths = vehicle_manager.get_queue_lengths()
        light_states = light_manager.get_light_states()
        light_stops = light_manager.get_waiting_stats()

        if not self._started:
            self._recorded_arrivals = stats.get("arrived", 0)
            self._started = True

        self.elapsed += dt
        self._sample_timer += dt
        self.latest_stats = dict(stats)

        self._record_vehicle_times(dt, stats, vehicles)
        self._record_queue_times(dt, stats, queue_lengths)
        self._record_light_states(dt, light_states)

        self.last_light_stop_events = dict(light_stops)
        self.latest_observation = self._make_observation(
            stats,
            vehicles,
            queue_lengths,
            light_states,
            light_stops,
            vehicle_manager,
            light_manager,
        )

        if self._sample_timer >= self.sample_interval:
            self._sample_timer = 0.0
            self.snapshots.append(self._make_snapshot(stats))

        return self.latest_observation

    def summary(self) -> dict:
        elapsed = max(self.elapsed, 1e-9)
        spawned = max(self.latest_stats.get("spawned", 0), 1)
        active_time = max(self.active_vehicle_time, 1e-9)
        arrived = self.latest_stats.get("arrived", 0)

        return {
            "duration_s": self._round(self.elapsed),
            "spawned": self.latest_stats.get("spawned", 0),
            "arrived": arrived,
            "active": self.latest_stats.get("total", 0),
            "completion_rate": self._round(arrived / spawned),
            "throughput_per_min": self._round(arrived / (elapsed / 60.0)),
            "avg_trip_time_s": self._avg(self.trip_times),
            "median_trip_time_s": self._median(self.trip_times),
            "avg_queue_length": self._round(self.queue_vehicle_time / elapsed),
            "max_queue_length": self.max_queue,
            "avg_waiting_at_lights": self._round(self.light_wait_vehicle_time / elapsed),
            "max_waiting_at_light": self.max_waiting_at_light,
            "avg_light_wait_s": self._avg(self.completed_light_waits),
            "avg_wait_time_per_spawned_s": self._round(self.light_wait_vehicle_time / spawned),
            "avg_stop_time_per_spawned_s": self._round(self.stopped_vehicle_time / spawned),
            "avg_speed_m_s": self._round(self.distance_sum / active_time),
            "congestion_ratio": self._round(self.stopped_vehicle_time / active_time),
            "per_light": self._per_light_summary(elapsed),
        }

    def controller_observation(self) -> dict:
        if self.latest_observation is None:
            return self._empty_observation().to_dict()
        return self.latest_observation.to_dict()

    def write_summary_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.summary(), f, indent=2)

    def write_observation_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.controller_observation(), f, indent=2)

    def write_snapshots_csv(self, path: str) -> None:
        if not self.snapshots:
            return
        with open(path, "w", newline="") as f:
            fieldnames = list(self.snapshots[0].to_dict().keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for snapshot in self.snapshots:
                writer.writerow(snapshot.to_dict())

    def _record_vehicle_times(self, dt: float, stats: dict, vehicles: list) -> None:
        active = stats.get("total", 0)
        stopped = stats.get("stopped", 0)
        waiting = stats.get("at_light", 0)

        self.active_vehicle_time += active * dt
        self.stopped_vehicle_time += stopped * dt
        self.light_wait_vehicle_time += waiting * dt
        self.distance_sum += sum(max(0.0, getattr(v, "speed", 0.0)) for v in vehicles) * dt
        self.max_waiting_at_light = max(self.max_waiting_at_light, waiting)

        current_ids = set()
        current_wait_keys = set()

        for vehicle in vehicles:
            vid = vehicle.vehicle_id
            current_ids.add(vid)
            self._last_seen_travel_time[vid] = getattr(vehicle, "travel_time", 0.0)

            if self._state_name(vehicle) == "arrived":
                self._record_trip_time(vid, getattr(vehicle, "travel_time", 0.0))

            light_id = getattr(vehicle, "queue_light_node", -1)
            if getattr(vehicle, "waiting_at_light", False) and light_id != -1:
                key = (vid, light_id)
                current_wait_keys.add(key)
                self._current_light_waits[key] = (
                    self._current_light_waits.get(key, 0.0) + dt
                )

        for key in list(self._current_light_waits):
            if key in current_wait_keys:
                continue
            _, light_id = key
            wait_time = self._current_light_waits.pop(key)
            self.completed_light_waits.append(wait_time)
            self.completed_waits_by_light.setdefault(light_id, []).append(wait_time)

        arrived_total = stats.get("arrived", 0)
        missing_ids = set(self._last_seen_travel_time) - current_ids
        arrivals_to_record = max(0, arrived_total - self._recorded_arrivals)

        for vid in sorted(missing_ids):
            if arrivals_to_record <= 0:
                break
            if vid in self._recorded_vehicle_ids:
                continue
            self._record_trip_time(vid, self._last_seen_travel_time.get(vid, 0.0) + dt)
            arrivals_to_record -= 1

        self._recorded_arrivals = max(self._recorded_arrivals, arrived_total)

        for vid in list(missing_ids):
            if vid in self._recorded_vehicle_ids:
                self._last_seen_travel_time.pop(vid, None)

    def _record_queue_times(self, dt: float, stats: dict,
                            queue_lengths: Dict[int, int]) -> None:
        queued = stats.get("queued", 0)
        self.queue_vehicle_time += queued * dt
        self.max_queue = max(self.max_queue, stats.get("max_queue", 0))

        for light_id, length in queue_lengths.items():
            self.queue_time_by_light[light_id] = (
                self.queue_time_by_light.get(light_id, 0.0) + length * dt
            )
            self.max_queue_by_light[light_id] = max(
                self.max_queue_by_light.get(light_id, 0),
                length,
            )

    def _record_light_states(self, dt: float, light_states: Dict[int, dict]) -> None:
        for light_id, data in light_states.items():
            state = data.get("state")
            if state is None:
                continue
            state_times = self.state_time_by_light.setdefault(light_id, {})
            state_times[state] = state_times.get(state, 0.0) + dt

    def _make_observation(self, stats: dict, vehicles: list,
                          queue_lengths: Dict[int, int],
                          light_states: Dict[int, dict],
                          light_stops: Dict[int, int],
                          vehicle_manager,
                          light_manager) -> TrafficObservation:
        approaching = self._count_approaching_vehicles(
            vehicles,
            vehicle_manager,
            light_manager,
        )
        current_waits = self._current_waits_by_light()

        lights: Dict[int, LightObservation] = {}
        for light_id, data in light_states.items():
            waits = current_waits.get(light_id, [])
            queue_length = queue_lengths.get(light_id, 0)
            oldest_wait = max(waits, default=0.0)
            avg_wait = mean(waits) if waits else 0.0

            green_ratio, yellow_ratio, red_ratio = self._light_ratios(light_id)
            pressure = self._pressure_score(
                queue_length,
                approaching.get(light_id, 0),
                oldest_wait,
            )

            lights[light_id] = LightObservation(
                light_id=light_id,
                state=data.get("state"),
                time_remaining=data.get("time_remaining", 0.0),
                queue_length=queue_length,
                approaching=approaching.get(light_id, 0),
                waiting=len(waits),
                oldest_wait_s=oldest_wait,
                avg_wait_s=avg_wait,
                stop_events=light_stops.get(light_id, 0),
                max_queue_length=self.max_queue_by_light.get(light_id, 0),
                pressure=pressure,
                green_ratio=green_ratio,
                yellow_ratio=yellow_ratio,
                red_ratio=red_ratio,
                group_id=data.get("group_id"),
                group_phase=data.get("group_phase"),
                controlled_from_nodes=data.get("controlled_from_nodes", []),
            )

        return TrafficObservation(
            time=self.elapsed,
            active=stats.get("total", 0),
            spawned=stats.get("spawned", 0),
            arrived=stats.get("arrived", 0),
            moving=stats.get("moving", 0),
            stopped=stats.get("stopped", 0),
            braking=stats.get("braking", 0),
            queued=stats.get("queued", 0),
            max_queue=stats.get("max_queue", 0),
            lights=lights,
        )

    def _make_snapshot(self, stats: dict) -> MetricSnapshot:
        elapsed = max(self.elapsed, 1e-9)
        active_time = max(self.active_vehicle_time, 1e-9)

        return MetricSnapshot(
            time=self.elapsed,
            active=stats.get("total", 0),
            spawned=stats.get("spawned", 0),
            arrived=stats.get("arrived", 0),
            moving=stats.get("moving", 0),
            stopped=stats.get("stopped", 0),
            braking=stats.get("braking", 0),
            queued=stats.get("queued", 0),
            max_queue=stats.get("max_queue", 0),
            throughput_per_min=stats.get("arrived", 0) / (elapsed / 60.0),
            avg_queue_length=self.queue_vehicle_time / elapsed,
            avg_waiting_at_lights=self.light_wait_vehicle_time / elapsed,
            avg_speed_m_s=self.distance_sum / active_time,
            congestion_ratio=self.stopped_vehicle_time / active_time,
        )

    def _per_light_summary(self, elapsed: float) -> Dict[int, dict]:
        result = {}
        light_ids = (
            set(self.queue_time_by_light)
            | set(self.state_time_by_light)
            | set(self.last_light_stop_events)
        )

        for light_id in sorted(light_ids):
            green_ratio, yellow_ratio, red_ratio = self._light_ratios(light_id)
            waits = self.completed_waits_by_light.get(light_id, [])
            result[light_id] = {
                "avg_queue_length": self._round(
                    self.queue_time_by_light.get(light_id, 0.0) / elapsed
                ),
                "max_queue_length": self.max_queue_by_light.get(light_id, 0),
                "stop_events": self.last_light_stop_events.get(light_id, 0),
                "avg_light_wait_s": self._avg(waits),
                "green_ratio": self._round(green_ratio),
                "yellow_ratio": self._round(yellow_ratio),
                "red_ratio": self._round(red_ratio),
            }

        return result

    def _count_approaching_vehicles(self, vehicles: list,
                                    vehicle_manager,
                                    light_manager) -> Dict[int, int]:
        graph = getattr(vehicle_manager, "graph", None)
        if graph is None:
            return {}

        counts: Dict[int, int] = {}
        for vehicle in vehicles:
            if getattr(vehicle, "waiting_at_light", False):
                continue
            if self._state_name(vehicle) in ("arrived", "no_path"):
                continue

            light_id = getattr(vehicle, "seg_to", -1)
            from_node = getattr(vehicle, "seg_from", -1)
            if light_id == -1 or from_node == -1:
                continue
            if not light_manager.has_light(light_id):
                continue

            light = light_manager.get_light(light_id)
            if light is not None and not light.is_approached_from(from_node):
                continue

            target = graph.nodes.get(light_id)
            if target is None:
                continue

            dist = _distance_m(vehicle.lat, vehicle.lon, target.lat, target.lon)
            if dist <= self.approach_radius_m:
                counts[light_id] = counts.get(light_id, 0) + 1

        return counts

    def _current_waits_by_light(self) -> Dict[int, List[float]]:
        waits: Dict[int, List[float]] = {}
        for (_, light_id), wait_time in self._current_light_waits.items():
            waits.setdefault(light_id, []).append(wait_time)
        return waits

    def _light_ratios(self, light_id: int) -> Tuple[float, float, float]:
        state_times = self.state_time_by_light.get(light_id, {})
        total = sum(state_times.values())
        if total <= 0.0:
            return 0.0, 0.0, 0.0
        return (
            state_times.get("green", 0.0) / total,
            state_times.get("yellow", 0.0) / total,
            state_times.get("red", 0.0) / total,
        )

    def _pressure_score(self, queue_length: int,
                        approaching: int,
                        oldest_wait_s: float) -> float:
        return (
            queue_length * QUEUE_WEIGHT
            + approaching * APPROACH_WEIGHT
            + oldest_wait_s * WAIT_WEIGHT
        )

    def _record_trip_time(self, vehicle_id: int, travel_time: float) -> None:
        if vehicle_id in self._recorded_vehicle_ids:
            return
        self._recorded_vehicle_ids.add(vehicle_id)
        if travel_time > 0.0:
            self.trip_times.append(travel_time)

    def _empty_observation(self) -> TrafficObservation:
        return TrafficObservation(
            time=self.elapsed,
            active=0,
            spawned=0,
            arrived=0,
            moving=0,
            stopped=0,
            braking=0,
            queued=0,
            max_queue=0,
            lights={},
        )

    @staticmethod
    def _state_name(vehicle) -> str:
        state = getattr(vehicle, "state", "")
        return str(getattr(state, "name", state)).lower()

    @staticmethod
    def _round(value: float) -> float:
        return round(float(value), 3)

    def _avg(self, values: List[float]) -> float:
        return self._round(mean(values)) if values else 0.0

    def _median(self, values: List[float]) -> float:
        return self._round(median(values)) if values else 0.0


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * earth_radius * math.asin(math.sqrt(a))
