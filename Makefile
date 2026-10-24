# GlucoTwin AI — Make targets (Windows notes included; run from project root)
# On Windows use PowerShell:  .\.venv\Scripts\python -m ...
PY?=python
VENV=.venv

.PHONY: setup data train test api build diagram slides clean

## Create a virtualenv and install backend dependencies
setup:
	$(PY) -m venv $(VENV)
	$(VENV)/Scripts/python -m pip install --upgrade pip
	$(VENV)/Scripts/python -m pip install -r requirements.txt -r requirements-docs.txt
	cd frontend && npm install

## Regenerate the synthetic dataset (seed 42, reproducible)
data:
	$(VENV)/Scripts/python -m backend.scripts.generate_data

## Train all horizon models and write metrics.json
train:
	$(VENV)/Scripts/python -m backend.scripts.train_model

## Run the backend test suite (90 tests; frontend has 46 Vitest tests)
test:
	$(VENV)/Scripts/python -m pytest tests -q

## Start the API server on :8000
api:
	$(VENV)/Scripts/python -m uvicorn backend.app.main:app --reload --port 8000

## Build the frontend bundle into frontend/dist
build:
	cd frontend && npm run build

## Regenerate the architecture diagram (PNG/SVG/PDF)
diagram:
	$(VENV)/Scripts/python -m docs.architecture.build_architecture_diagram