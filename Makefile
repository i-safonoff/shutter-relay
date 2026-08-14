.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: up
up:  ## Full stack: Postgres, Redis, MinIO, imgproxy, the app, nginx
	$(COMPOSE) up -d --build

.PHONY: down
down:  ## Stop it
	$(COMPOSE) down -v

.PHONY: infra
infra:  ## Just the backing services, for running the app locally with manage.py
	$(COMPOSE) up -d postgres redis minio imgproxy

.PHONY: migrate
migrate:  ## Apply migrations against infra started with `make infra`
	python manage.py migrate

.PHONY: bootstrap
bootstrap:  ## Create the S3 bucket
	python manage.py bootstrap_storage

.PHONY: dev
dev:  ## Run the app locally against `make infra` (not the containerized one)
	daphne -b 0.0.0.0 -p 8010 relay.asgi:application

.PHONY: test
test:  ## Everything that needs no containers
	pytest -m "not live"

.PHONY: test-all
test-all:  ## Including the live flow against the real stack
	pytest

.PHONY: lint
lint:  ## Ruff
	ruff check .
	ruff format --check .
