.PHONY: init images up down dev worker baseline test test-docker lint

init:
	git submodule update --init --recursive
	python3 scripts/setup.py

images:
	python3 scripts/build_images.py

up:
	docker compose up --build -d

down:
	docker compose down

dev:
	uv run uvicorn rx_oj.api:app --host 127.0.0.1 --port 8000 --reload

worker:
	uv run python -m rx_oj.worker

baseline:
	docker compose run --rm --no-deps baseline

test:
	uv run pytest -m 'not docker'

test-docker:
	OJ_TEST_DOCKER=1 uv run pytest -m docker

lint:
	uv run ruff check .
	uv run ruff format --check .
	node --check rx_oj/static/app.js
