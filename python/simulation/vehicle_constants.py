"""Constantes utilisées par la logique des véhicules.

Toutes les distances sont en metres et les vitesses en m/s. Les
constantes de geographie M_PER_DEG_* sont calees sur la latitude
de Paris (48.85 N).
"""

import math


# Dimensions et marges de securite entre vehicules
VEHICLE_LENGTH = 4.5             # longueur moyenne d'une voiture
SAFE_GAP = 5.0                   # gap minimal toujours conserve
BRAKE_DISTANCE = 35.0            # gap en dessous duquel on commence a freiner

# Geometrie des files devant les feux
QUEUE_SLOT = VEHICLE_LENGTH + 2.0   # espacement entre vehicules empiles
QUEUE_JOIN_DIST = 80.0              # distance a partir de laquelle on rejoint la file
STOP_LINE_DIST = 4.0                # distance d'arret avant le feu
LIGHT_BRAKE_DIST = 50.0             # distance d'approche prudente d'un feu rouge

# Reservation aux intersections sans feu
INTER_RESERVE_DIST = 20.0    # distance avant le noeud ou on tente de reserver
INTER_CLEAR_DIST = 3.0       # distance apres laquelle on libere le token
INTER_YIELD_TIMEOUT = 8.0    # une voiture qui cede depuis trop longtemps finit par passer

# Limites cinematiques (m/s^2 et m/s)
MAX_ACCEL = 2.5
MAX_DECEL = 5.5
MIN_SPEED = 0.1

# Garde-fou : nombre max de segments traverses dans un meme tick
MAX_SEGS_PER_TICK = 5

QUEUE_RELEASE_COOLDOWN = 2.0   # delai entre deux liberations consecutives

# Penalites injectees dans Dijkstra pour repartir les nouveaux trajets
# loin des zones saturees. Plus une rue est congestionnee, plus elle
# devient couteuse a emprunter.
CONGESTION_VEHICLE_PENALTY = 2.0
CONGESTION_BRAKING_PENALTY = 4.0
CONGESTION_STOPPED_PENALTY = 7.0
CONGESTION_QUEUE_PENALTY = 6.0
CONGESTION_ROAD_FACTOR = 0.25

# Un segment "receveur" est considere plein a 85 % de sa capacite,
# pour eviter qu'un vehicule ne se gare litteralement sur le precedent
RECEIVING_SEGMENT_FILL_RATIO = 0.85

# Conversion lat/lon -> metres a la latitude de Paris
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(48.85))
