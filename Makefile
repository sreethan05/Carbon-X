# CarbonX DevOps Makefile
.PHONY: help build up down restart logs ps test lint clean dev down-dev

help:
	@echo "CarbonX DevOps Commands:"
	@echo "  make build       - Build all Docker images"
	@echo "  make up          - Start all services in production mode (daemon)"
	@echo "  make down        - Stop all production services"
	@echo "  make dev         - Start all services in development mode with hot-reloading"
	@echo "  make down-dev    - Stop development services"
	@echo "  make restart     - Restart all services"
	@echo "  make logs        - Follow logs across all containers"
	@echo "  make ps          - View container status and health"
	@echo "  make test        - Run test suites across blockchain and backend"
	@echo "  make lint        - Run linting checks"
	@echo "  make clean       - Remove containers, volumes, and temporary build caches"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

dev:
	docker compose -f docker-compose.dev.yml up --build

down-dev:
	docker compose -f docker-compose.dev.yml down

logs:
	docker compose logs -f

ps:
	docker compose ps

test:
	@echo "Running backend test suite..."
	cd backend && python -m unittest discover tests -v
	@echo "Running smart contract test suite..."
	cd blockchain && npm test

lint:
	npm run lint

clean:
	docker compose down -v --remove-orphans
	docker compose -f docker-compose.dev.yml down -v --remove-orphans
