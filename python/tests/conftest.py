"""Configuration de chemin pour lancer les tests depuis la racine du projet."""
import os
import sys

# Permet aux tests d'importer les modules du dossier parent (python/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
