

PYTHON      := python3
VENV_DIR    := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP    := $(VENV_DIR)/bin/pip

SRC_DIR     := python
DATA_DIR    := data

OSM_RAW     := $(DATA_DIR)/paris13.json
MAP_CLEAN   := $(DATA_DIR)/map_clean.json
REQ_FILE    := $(SRC_DIR)/requirements.txt

.DEFAULT_GOAL := help
.PHONY: help venv install setup fetch build data run console clean reset-venv check all



help:
	@echo ""
	@echo "Paris 13e — Traffic Simulator"
	@echo ""
	@echo "Commandes principales :"
	@echo "  make run        Lancer la simulation (GUI Pygame)"
	@echo "  make console    Lancer en mode console"
	@echo "  make all        Setup + données + run"
	@echo ""
	@echo "Setup :"
	@echo "  make setup      Créer le venv + installer les dépendances"
	@echo "  make reset-venv Recréer le virtualenv"
	@echo ""
	@echo "Données :"
	@echo "  make fetch      Télécharger les données OSM"
	@echo "  make build      Générer map_clean.json"
	@echo "  make data       fetch + build"
	@echo ""
	@echo "Maintenance :"
	@echo "  make clean      Supprimer les fichiers temporaires"
	@echo "  make check      Vérifier la syntaxe Python"
	@echo ""



venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo " Création du virtualenv..."; \
		$(PYTHON) -m venv $(VENV_DIR); \
	fi

install: venv
	@echo " Installation des dépendances..."
	@$(VENV_PIP) install --upgrade pip
	@$(VENV_PIP) install -r $(REQ_FILE)

setup: install
	@echo " Environnement prêt"


fetch: install
	@mkdir -p $(DATA_DIR)
	@echo " Téléchargement des données OSM..."
	@$(VENV_PYTHON) $(SRC_DIR)/fetch_osm.py

build: install
	@if [ ! -f "$(OSM_RAW)" ]; then \
		echo "ERREUR : paris13.json manquant (lancez make fetch)"; \
		exit 1; \
	fi
	@echo " Génération de map_clean.json..."
	@$(VENV_PYTHON) $(SRC_DIR)/clean_json.py $(OSM_RAW)

data: fetch build
	@echo "Données prêtes"



run: install
	@if [ ! -f "$(MAP_CLEAN)" ]; then \
		echo " Données manquantes, génération..."; \
		$(MAKE) data; \
	fi
	@echo " Lancement de la simulation (GUI)"
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) simulation_gui.py

console: install
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) main.py



clean:
	@find . -name "__pycache__" -type d -exec rm -rf {} +
	@find . -name "*.pyc" -delete
	@echo "Nettoyage terminé"

reset-venv:
	@rm -rf $(VENV_DIR)
	@$(MAKE) setup

check: install
	@$(VENV_PYTHON) -m py_compile $(SRC_DIR)/*.py
	@echo "Vérification OK"


all: setup data run
