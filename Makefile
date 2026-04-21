PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin

.DEFAULT_GOAL := help

.PHONY: help install install-dev run lint format hooks clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: $(BIN)/python  ## Install the tool (editable) and runtime dependencies
	$(BIN)/pip install -e .

install-dev: install  ## Install development dependencies as well
	$(BIN)/pip install -r requirements-dev.txt

run:  ## Execute the migrator (requires a populated .env)
	$(BIN)/python -m spotify_migration

lint:  ## Run ruff lint + format check
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format:  ## Apply ruff formatting and auto-fixes
	$(BIN)/ruff format .
	$(BIN)/ruff check --fix .

hooks:  ## Install pre-commit hooks
	$(BIN)/pre-commit install

clean:  ## Remove caches and build artifacts
	rm -rf __pycache__ .ruff_cache .pytest_cache build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
