# One command to a working checkout: `make setup`, then `make up`.
# Every target is safe to run twice.

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

VENV    := backend/.venv
PY      := $(VENV)/bin/python
COMPOSE := docker compose

-include .env
export

.PHONY: help setup env deps db migrate migration up down logs ps \
        test test-backend test-frontend e2e lint fmt admin shell psql

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: env deps db migrate  ## .env, dependencies, database, schema

env:  ## Create .env from .env.example if missing
	@[ -f .env ] || { cp .env.example .env; echo "created .env"; }

deps: $(VENV)  ## Install backend and frontend dependencies
	@cd frontend && npm ci --no-audit --no-fund

$(VENV):
	python3.13 -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r backend/requirements-dev.txt

db:  ## Start Postgres and wait for it
	@docker info >/dev/null 2>&1 || { echo "Start Docker first."; exit 1; }
	@$(COMPOSE) up -d db
	@for i in $$(seq 1 30); do \
		$(COMPOSE) exec -T db pg_isready -q -U "$${POSTGRES_USER:-gymbahi}" && exit 0; \
		sleep 1; done; echo "postgres did not start: make logs"; exit 1

migrate:  ## Apply migrations (host venv)
	@cd backend && ../$(PY) -m alembic upgrade head

migration:  ## New migration from model changes: make migration m="add members"
	@cd backend && ../$(PY) -m alembic revision --autogenerate -m "$(m)"

up:  ## Start db, api, worker and web
	@# -V renews the node_modules volume, or new packages stay hidden behind the old one.
	@$(COMPOSE) up -d --build --renew-anon-volumes
	@echo "  web  http://localhost:$${WEB_PORT:-3000}"
	@echo "  api  http://localhost:$${API_PORT:-8000}/docs"

down:  ## Stop everything, keeping data
	@$(COMPOSE) down

logs:  ## Follow logs
	@$(COMPOSE) logs -f

ps:  ## What is running
	@$(COMPOSE) ps

test: test-backend test-frontend  ## Backend and frontend tests

test-backend:  ## pytest (needs `make db`)
	@cd backend && ../$(PY) -m pytest -q

test-frontend:  ## Vitest
	@cd frontend && npm test --silent

e2e:  ## Playwright against the running stack (`make up` first)
	@cd frontend && npx playwright test

lint:  ## ruff, eslint, tsc
	@cd backend && ../$(PY) -m ruff check app tests scripts alembic \
		&& ../$(PY) -m ruff format --check app tests scripts alembic
	@cd frontend && npm run -s lint && npm run -s typecheck

fmt:  ## Format both sides
	@cd backend && ../$(PY) -m ruff check --fix app tests scripts alembic \
		&& ../$(PY) -m ruff format app tests scripts alembic
	@cd frontend && npm run -s format

admin:  ## Create a platform admin: make admin name="Ramesh" email=you@example.com
	@$(COMPOSE) exec api python -m scripts.create_platform_admin \
		--name "$(name)" $(if $(email),--email $(email)) $(if $(phone),--phone $(phone))

shell:  ## Shell in the api container
	@$(COMPOSE) exec api bash

psql:  ## psql into the dev database
	@$(COMPOSE) exec db psql -U "$${POSTGRES_USER:-gymbahi}" "$${POSTGRES_DB:-gymbahi}"
