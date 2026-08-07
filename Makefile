.PHONY: setup lint format test secretos bd bd-parar limpiar api

setup:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt

lint:
	ruff check .

format:
	ruff format .

test:
	pytest -q

secretos:
	bash tools/verificar_secretos.sh

bd:
	docker compose up -d

bd-parar:
	docker compose stop

api:
	uvicorn apps.api.main:app --reload

limpiar:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name ".DS_Store" -delete
