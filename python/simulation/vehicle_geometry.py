"""Petits calculs géométriques et cinématiques des véhicules."""

import math
from typing import Tuple

from simulation.vehicle_constants import (
    BRAKE_DISTANCE,
    M_PER_DEG_LAT,
    M_PER_DEG_LON,
    MAX_ACCEL,
    MAX_DECEL,
    MIN_SPEED,
    SAFE_GAP,
)
from simulation.vehicle_model import Vehicle, VehicleState


def _seg_dir_meters(fn, tn) -> Tuple[float, float, bool]:
    """
    Vecteur unitaire du segment fn -> tn.
    ux représente l'axe Est/Ouest, uy l'axe Nord/Sud.
    """
    if fn is None or tn is None:
        return 0.0, 0.0, False

    dx = (tn.lon - fn.lon) * M_PER_DEG_LON
    dy = (tn.lat - fn.lat) * M_PER_DEG_LAT
    n = math.sqrt(dx * dx + dy * dy)
    if n < 1e-6:
        return 0.0, 0.0, False
    return dx / n, dy / n, True


def _dot_to_other_meters(v: Vehicle, other: Vehicle,
                         ux: float, uy: float) -> float:
    dx = (other.lon - v.lon) * M_PER_DEG_LON
    dy = (other.lat - v.lat) * M_PER_DEG_LAT
    return dx * ux + dy * uy


def _speed_for_gap(gap: float, max_speed: float) -> float:
    if gap <= SAFE_GAP:
        return 0.0
    if gap >= BRAKE_DISTANCE:
        return max_speed
    return max_speed * (gap - SAFE_GAP) / (BRAKE_DISTANCE - SAFE_GAP)


def _apply_speed(v: Vehicle, desired: float, dt: float) -> None:
    if desired <= 0.0:
        v.speed = max(0.0, v.speed - MAX_DECEL * dt)
        if v.speed < MIN_SPEED:
            v.speed = 0.0
            v.state = VehicleState.STOPPED
        else:
            v.state = VehicleState.BRAKING
    elif v.speed < desired:
        v.speed = min(desired, v.speed + MAX_ACCEL * dt)
        v.state = VehicleState.MOVING
    elif v.speed > desired:
        v.speed = max(desired, v.speed - MAX_DECEL * dt)
        v.state = VehicleState.BRAKING
    else:
        v.state = VehicleState.MOVING
