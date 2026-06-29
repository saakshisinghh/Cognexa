.PHONY: help dev build up down logs clean seed test lint

# Default target
help:
	@echo ""
	@echo "  INDUS MIND — Makefile Commands"
	@echo ""
	@echo "  make dev          Start all services in development mode"
	@echo "  make up           Start all services (detached)"
	@echo "  make down         Stop all services"
	@echo "  make build        Build all Docker images"
	@echo "  make logs         Tail logs from all services"
	@echo "  make logs-api     Tail API logs only"
	@echo "  make logs-web     Tail web logs only"
	@echo "  make clean        Remove containers, volumes, and caches"
	@echo "  make seed         Seed a demo admin user"
	@echo "  make test         Run all tests"
	@echo "  make test-api     Run Python tests only"
	@echo "  make lint         Run linters (Python + TypeScript)"
	@echo "  make shell-api    Open a shell in the API container"
	@echo "  make db-shell     Open a psql shell"
	@echo ""

# ─── Docker Operations ────────────────────────────────────────────────────────

dev:
	@cp -n .env.example .env 2>/dev/null || true
	docker compose up --build

up:
	@cp -n .env.example .env 2>/dev/null || true
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

logs-web:
	docker compose logs -f web

restart:
	docker compose restart

restart-api:
	docker compose restart api

# ─── Database ─────────────────────────────────────────────────────────────────

db-shell:
	docker compose exec postgres psql -U indusmind -d indusmind

db-migrate:
	docker compose exec api alembic upgrade head

db-reset:
	docker compose down -v
	docker compose up -d postgres
	@sleep 5
	docker compose up -d

# ─── Seed ─────────────────────────────────────────────────────────────────────

seed:
	@echo "Creating demo admin user..."
	docker compose exec api python -c " \
import sys; sys.path.insert(0, '.'); \
from apps.api.db import SessionLocal; \
from apps.api.models import User, UserRole; \
from apps.api.routers.auth import hash_password; \
db = SessionLocal(); \
existing = db.query(User).filter(User.email == 'admin@indusmind.io').first(); \
if existing: print('Admin already exists'); \
else: \
  u = User(email='admin@indusmind.io', full_name='INDUS MIND Admin', \
    hashed_password=hash_password('admin1234'), role=UserRole.admin); \
  db.add(u); db.commit(); print('Admin created: admin@indusmind.io / admin1234'); \
db.close()"

# ─── Testing ──────────────────────────────────────────────────────────────────

test:
	make test-api

test-api:
	docker compose exec api python -m pytest apps/api/tests/ -v --tb=short

# ─── Code Quality ─────────────────────────────────────────────────────────────

lint:
	@echo "Running Python linting..."
	docker compose exec api python -m flake8 apps/api/ --max-line-length=120 --exclude=__pycache__
	@echo "Running TypeScript type check..."
	docker compose exec web npm run type-check

# ─── Shells ───────────────────────────────────────────────────────────────────

shell-api:
	docker compose exec api bash

shell-web:
	docker compose exec web sh

# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean:
	docker compose down -v --remove-orphans
	docker system prune -f
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true

# ─── Health ───────────────────────────────────────────────────────────────────

health:
	@curl -s http://localhost:8000/api/health | python3 -m json.tool
