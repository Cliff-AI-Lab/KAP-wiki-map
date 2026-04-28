# KAP Backend Makefile · v1.0.0-m0
PROJECT := kap-backend
IMAGE   := kap/backend:v1.0.0-m0

.PHONY: install dev infra infra-down api demo test lint frontend-install frontend-dev frontend-build

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

infra:
	docker compose up -d

infra-down:
	docker compose down

api:
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

demo:
	python -m scripts.demo_e2e

init-db:
	python -m scripts.init_db

test:
	pytest tests/ -v --tb=short

lint:
	ruff check packages/ api/ workers/
	ruff format --check packages/ api/ workers/

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build
