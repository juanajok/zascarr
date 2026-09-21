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

# OJO: "alembic", nunca "python -m alembic". El directorio de migraciones
# del propio repo se llama alembic/ igual que el paquete instalado; dentro
# del contenedor (WORKDIR /app, con /app/alembic/) "python -m alembic"
# resuelve al directorio local (sin __main__.py) en vez de a la librería
# real, y falla con "cannot be directly executed". El binario alembic no
# sufre esto: su propio sys.path[0] es site-packages, no el cwd.
migrate:
	$(SA) alembic upgrade head

migrate-down:
	$(SA) alembic downgrade -1

migrate-status:
	$(SA) alembic current
	$(SA) alembic history --verbose

migration:
	$(SA) alembic revision --autogenerate -m "$(name)"

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
