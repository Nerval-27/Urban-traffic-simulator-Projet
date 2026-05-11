

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
RL_EPISODES   ?= 30
RL_MAX_TIME   ?= 120
RL_VEHICLES   ?= 80

BENCH_TIME     ?= 300
BENCH_VEHICLES ?= 100
BENCH_QTABLE   ?= results/q_table.json

.PHONY: help venv install setup fetch build data run console clean reset-venv check test rl-demo rl-train rl-bench rl-run rl-all all



help:
	@echo ""
	@echo "Paris 13e — Traffic Simulator"
	@echo ""
	@echo "Commandes principales :"
	@echo "  make run        Lancer la simulation (GUI Pygame, cycles fixes)"
	@echo "  make rl-run     Lancer la GUI avec l'agent RL aux commandes des feux"
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
	@echo "Apprentissage par renforcement :"
	@echo "  make rl-demo    Test rapide de l'environnement RL (politique aléatoire)"
	@echo "  make rl-train   Entraîner l'agent Q-learning"
	@echo "                  Variables : RL_EPISODES=$(RL_EPISODES) RL_MAX_TIME=$(RL_MAX_TIME) RL_VEHICLES=$(RL_VEHICLES)"
	@echo "                  Exemple   : make rl-train RL_EPISODES=50 RL_MAX_TIME=300"
	@echo "  make rl-bench   Comparer Baseline (cycles fixes) vs RL (Q-learning)"
	@echo "                  Variables : BENCH_TIME=$(BENCH_TIME) BENCH_VEHICLES=$(BENCH_VEHICLES) BENCH_QTABLE=$(BENCH_QTABLE)"
	@echo "  make rl-all     Pipeline complet : entraînement + benchmark"
	@echo ""
	@echo "Maintenance :"
	@echo "  make clean      Supprimer les fichiers temporaires"
	@echo "  make check      Vérifier la syntaxe Python"
	@echo "  make test       Lancer les tests unitaires"
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
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) -m data_tools.fetch_osm

build: install
	@if [ ! -f "$(OSM_RAW)" ]; then \
		echo "ERREUR : paris13.json manquant (lancez make fetch)"; \
		exit 1; \
	fi
	@echo " Génération de map_clean.json..."
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) -m data_tools.clean_json $(abspath $(OSM_RAW))

data: fetch build
	@echo "Données prêtes"



run: install
	@if [ ! -f "$(MAP_CLEAN)" ]; then \
		echo " Données manquantes, génération..."; \
		$(MAKE) data; \
	fi
	@echo " Lancement de la simulation (GUI)"
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) -m gui.app

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
	@find $(SRC_DIR) -name "*.py" -not -path "*/__pycache__/*" \
	    -exec $(VENV_PYTHON) -m py_compile {} +
	@echo "Vérification OK"

test: install
	@if [ ! -f "$(MAP_CLEAN)" ]; then \
		echo " Données manquantes, génération..."; \
		$(MAKE) data; \
	fi
	@echo " Lancement des tests"
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) -m unittest discover tests/ -v


rl-demo: install
	@if [ ! -f "$(MAP_CLEAN)" ]; then \
		echo " Données manquantes, génération..."; \
		$(MAKE) data; \
	fi
	@echo " Test de l'environnement RL (politique aléatoire)"
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) -m rl.demo

rl-train: install
	@if [ ! -f "$(MAP_CLEAN)" ]; then \
		echo " Données manquantes, génération..."; \
		$(MAKE) data; \
	fi
	@echo " Entraînement Q-learning : $(RL_EPISODES) épisodes de $(RL_MAX_TIME)s"
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) -m rl.train $(RL_EPISODES) \
	    --max-time $(RL_MAX_TIME) --vehicles $(RL_VEHICLES)

rl-bench: install
	@if [ ! -f "$(MAP_CLEAN)" ]; then \
		echo " Données manquantes, génération..."; \
		$(MAKE) data; \
	fi
	@if [ ! -f "$(BENCH_QTABLE)" ]; then \
		echo "ERREUR : Q-table introuvable ($(BENCH_QTABLE))"; \
		echo "Lancez d'abord : make rl-train"; \
		exit 1; \
	fi
	@echo " Benchmark Baseline vs RL : $(BENCH_TIME)s, $(BENCH_VEHICLES) véhicules"
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) -m rl.benchmark \
	    --qtable $(abspath $(BENCH_QTABLE)) \
	    --max-time $(BENCH_TIME) --vehicles $(BENCH_VEHICLES)

rl-run: install
	@if [ ! -f "$(MAP_CLEAN)" ]; then \
		echo " Données manquantes, génération..."; \
		$(MAKE) data; \
	fi
	@if [ ! -f "$(BENCH_QTABLE)" ]; then \
		echo "ERREUR : Q-table introuvable ($(BENCH_QTABLE))"; \
		echo "Lancez d'abord : make rl-train"; \
		exit 1; \
	fi
	@echo " GUI Pygame avec agent RL"
	@cd $(SRC_DIR) && $(abspath $(VENV_PYTHON)) -m gui.app \
	    --mode rl --qtable $(abspath $(BENCH_QTABLE))

rl-all:
	@$(MAKE) rl-train
	@$(MAKE) rl-bench


all: setup data run
