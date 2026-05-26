.PHONY: up down test seed logs shell migrate

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f backend

shell:
	docker compose exec backend bash

migrate:
	docker compose exec backend alembic upgrade head

seed:
	docker compose exec backend python -m app.seeds.seed_mock_data
	docker compose exec backend python -m app.seeds.seed_agents
	docker compose exec backend python -m app.seeds.seed_workflows
	docker compose exec backend python -m app.seeds.seed_routing_rules

test:
	docker compose exec backend pytest tests/ -v

dev:
	docker compose up postgres -d && \
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
