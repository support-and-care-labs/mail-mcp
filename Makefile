#
# Copyright 2025 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

.PHONY: all install lint typecheck test test-all build docker clean help

# Default target
all: lint typecheck test

# Install dependencies (dev mode)
install:
	pip install -e ".[dev]"

# Linting with ruff
lint:
	ruff check src/ tests/

# Type checking with mypy
typecheck:
	mypy src/ --ignore-missing-imports

# Unit tests only (fast, no external deps)
test:
	pytest tests/unit/ -v --tb=short

# All tests including integration (requires Docker for Testcontainers)
test-all:
	pytest tests/ -v --tb=short

# Build Python package
build:
	python -m build

# Build Docker image
docker:
	docker build -t mail-mcp:local .

# Run Docker image locally
docker-run:
	docker run --rm -it -p 58080:8080 mail-mcp:local

# Clean build artifacts
clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# CI target (what GitHub Actions runs)
ci: lint typecheck test

# Help
help:
	@echo "Available targets:"
	@echo "  all        - Run lint, typecheck, and test (default)"
	@echo "  install    - Install package in dev mode with dependencies"
	@echo "  lint       - Run ruff linter"
	@echo "  typecheck  - Run mypy type checker"
	@echo "  test       - Run unit tests only"
	@echo "  test-all   - Run all tests (requires Docker for Testcontainers)"
	@echo "  build      - Build Python wheel and sdist"
	@echo "  docker     - Build Docker image locally"
	@echo "  docker-run - Run Docker image locally"
	@echo "  clean      - Remove build artifacts and caches"
	@echo "  ci         - Run CI checks (lint, typecheck, test)"
