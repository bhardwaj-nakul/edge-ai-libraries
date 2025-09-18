# Makefile for Traffic Intelligence Service
.PHONY: help setup run dev test lint clean docker example

help:  ## Show this help message
	@echo "Traffic Intelligence Service - Make Commands"
	@echo "============================================"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {# printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup:  ## Setup development environment with uv
	@./dev.sh setup

run:  ## Run the traffic intelligence service
	@./dev.sh run

dev:  ## Run in development mode (debug logging)
	@./dev.sh dev

test:  ## Run tests
	@./dev.sh test

lint:  ## Run linting and formatting
	@./dev.sh lint

example:  ## Run example client
	@./dev.sh example

clean:  ## Clean up virtual environment
	@./dev.sh clean

docker:  ## Build and run with Docker
	@./dev.sh docker

# Alternative commands using uv directly
uv-setup:  ## Setup with uv directly
	uv venv
	uv pip install -r requirements.txt

uv-run:  ## Run with uv directly
	uv run python run.py

uv-test:  ## Test with uv directly
	uv run pytest -v

# Docker commands
docker-build:  ## Build Docker image
	docker build -t traffic-intelligence .

docker-run:  ## Run Docker container
	docker run -p 8081:8081 traffic-intelligence

docker-compose-up:  ## Start with docker-compose
	docker-compose up -d

docker-compose-down:  ## Stop docker-compose services
	docker-compose down

# Health check
health:  ## Check service health
	curl -f http://localhost:8081/health || echo "Service not running"

status:  ## Check service status
	curl -s http://localhost:8081/api/v1/status | python -m json.tool || echo "Service not running"