.PHONY: db api ui test lint migrate

db:
	docker compose up -d postgres

db-stop:
	docker compose down

api:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

ui:
	cd frontend && npm run dev

test:
	cd backend && python -m pytest tests/ -v

lint:
	cd backend && ruff check app/ tests/

migrate:
	cd backend && alembic upgrade head

migration:
	cd backend && alembic revision --autogenerate -m "$(msg)"

install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && npm install

install: install-backend install-frontend
