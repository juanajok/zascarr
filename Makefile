COMPOSE = docker compose
SA      = $(COMPOSE) exec secuenciarr

.PHONY: help up down restart logs build migrate migrate-down migrate-status health shell db-shell test lint format backup

help:
	@echo "  up / down / restart / logs / build"
	@echo "  migrate / migrate-down / migrate-status"
	@echo "  health / shell / db-shell"
	@echo "  test / lint / format"
	@echo "  backup"

up:
	$(COMPOSE) up -d
	@echo "API: http://127.0.0.1:8000/api/docs"

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart secuenciarr

logs:
	$(COMPOSE) logs -f secuenciarr

build:
	$(COMPOSE) build secuenciarr

migrate:
	$(SA) python -m alembic upgrade head

migrate-down:
	$(SA) python -m alembic downgrade -1

migrate-status:
	$(SA) python -m alembic current
	$(SA) python -m alembic history --verbose

migration:
	$(SA) python -m alembic revision --autogenerate -m "$(name)"

health:
	@curl -sf http://127.0.0.1:8000/api/health | python3 -m json.tool

shell:
	$(SA) /bin/bash

db-shell:
	$(COMPOSE) exec postgres psql -U comics_admin -d tebeoteca

test:
	$(SA) python -m pytest tests/ -v

lint:
	$(SA) python -m ruff check src/

format:
	$(SA) python -m ruff format src/

backup:
	@TS=$$(date +%Y%m%d_%H%M%S); \
	$(COMPOSE) exec -T postgres pg_dump -U comics_admin tebeoteca | \
	gzip > /mnt/nvme/tebeoteca/config/postgres/backup_$${TS}.sql.gz && \
	echo "Backup: backup_$${TS}.sql.gz"
