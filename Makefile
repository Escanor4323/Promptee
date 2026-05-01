.PHONY: setup start stop test build clean go-test go-build

setup:
	pip install -r backend/requirements.txt

start:
	bash scripts/start_promptee.sh

stop:
	docker compose -f docker/docker-compose.milvus.yml down
	pkill -f "uvicorn app.main:app" 2>/dev/null || true

test:
	cd backend && python -m pytest tests/ -v --cov=app --cov-report=term-missing

build:
	cd cmd/promptee && go build -o ../../bin/promptee .

clean:
	rm -rf data/ bin/
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

go-build:
	go build -o bin/promptee ./cmd/promptee

go-test:
	go test -race ./...
