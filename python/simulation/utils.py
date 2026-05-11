import json
import sys
import math

def haversine(lat1, lon1, lat2, lon2):
    """Distance en mètres entre 2 points GPS."""
    R = 6371000  # rayon de la Terre
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

