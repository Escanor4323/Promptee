.PHONY: setup start stop test build rebuild clean go-test go-build

setup:
	pip install -r backend/requirements.txt

start:
	bash scripts/start_promptee.sh

stop:
	docker compose -f docker/docker-compose.milvus.yml down
	pkill -f "uvicorn app.main:app" 2>/dev/null || true

test:
	cd backend && python -m pytest tests/ -v --cov=app --cov-report=term-missing

# Build the CLI binary only (bin/promptee + ./promptee).
# Run this first, THEN use './promptee build all' for Docker.
build:
	go build -o bin/promptee ./cmd/promptee
	cp bin/promptee ./promptee
	@echo "✅  bin/promptee and ./promptee updated"

go-build: build

# Full rebuild: CLI binary first (while Docker is NOT re-building), then Docker.
# Running go build + docker build + Milvus simultaneously causes OOM / killed.
rebuild:
	$(MAKE) build
	./promptee build all

clean:
	rm -rf data/ bin/
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

go-test:
	go test -race ./...
