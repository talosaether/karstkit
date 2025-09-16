.PHONY: help bootstrap proto plan apply destroy test fmt clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Create venv, install deps, pre-commit install, generate proto
	python3 -m venv venv
	. venv/bin/activate && pip install --upgrade pip
	. venv/bin/activate && pip install -r requirements.txt
	. venv/bin/activate && pre-commit install
	. venv/bin/activate && make proto
	@echo "Bootstrap complete! Activate with: source venv/bin/activate"

proto: ## Compile protobufs to iac_wrapper/grpc_pb
	python3 -m grpc_tools.protoc \
		--python_out=iac_wrapper/grpc_pb \
		--grpc_python_out=iac_wrapper/grpc_pb \
		--proto_path=proto \
		proto/controlplane.proto
	touch iac_wrapper/grpc_pb/__init__.py

plan: ## Run terraform plan
	cd infra && terraform init
	cd infra && terraform plan

apply: ## Run terraform apply
	cd infra && terraform apply -auto-approve

destroy: ## Run terraform destroy
	cd infra && terraform destroy -auto-approve

test: ## Run tests
	pytest -v

test-cov: ## Run tests with coverage
	pytest --cov=iac_wrapper --cov-report=html

fmt: ## Format code with black
	black .

lint: ## Run linting
	black --check .
	flake8 iac_wrapper tests

clean: ## Clean up generated files
	rm -rf venv
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf iac_wrapper/grpc_pb/*.py
	rm -rf secrets/*
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +

dev: ## Start development server
	. venv/bin/activate && python -m iac_wrapper.api

install: ## Install the package in development mode
	pip install -e .

e2e-test: ## Run end-to-end deployment pipeline test
	python tests/test_e2e_deployment_pipeline.py

e2e-test-ci: ## Run e2e test with CI-friendly output
	python tests/test_e2e_deployment_pipeline.py 2>&1 | tee e2e-test.log
