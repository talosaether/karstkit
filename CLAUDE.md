# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Bootstrap
```bash
make bootstrap       # Setup virtual environment, install dependencies, pre-commit, and generate protobuf files
source venv/bin/activate  # Activate the virtual environment after bootstrap
```

### Code Quality
```bash
make fmt            # Format code with black
make lint           # Run linting checks (black --check, flake8)
make test           # Run pytest tests
make test-cov       # Run tests with coverage report
```

### Infrastructure and Deployment
```bash
make proto          # Compile protobufs to iac_wrapper/grpc_pb/
make plan           # Run terraform plan (shows infrastructure changes)
make apply          # Apply terraform configuration
make destroy        # Destroy all infrastructure resources

# CLI Commands (after activating venv)
iac deploy --file repos.yaml    # Deploy services from repository slugs
iac plan                         # Show terraform plan
iac health                       # Check health of deployed services
iac logs                         # Show logs from deployed services
iac destroy                      # Destroy all deployed resources
```

### Development Server
```bash
make dev            # Start Flask development server
make install        # Install package in development mode
```

## Architecture Overview

KarstKit is an Infrastructure-as-Code (IaC) deployment wrapper that:

1. **Parses repository slugs** in format `scheme:owner/repo[#ref]` (supports GitHub `gh:`, GitLab `gl:`)
2. **Fetches source code** using archive downloads (preferred) or shallow git clones
3. **Detects Python entrypoints** automatically through multiple strategies:
   - Console scripts in `pyproject.toml`
   - Package `__main__.py` files
   - Root `main.py` files
   - Function detection scanning
4. **Builds Docker containers** with Python 3.11-slim base and OpenTelemetry instrumentation
5. **Deploys with mTLS service mesh** using Envoy sidecars for secure inter-service communication
6. **Manages infrastructure** using Terraform with Docker provider

### Core Components

- **`iac_wrapper/slug.py`**: Repository slug parsing and validation
- **`iac_wrapper/gitops.py`**: Git operations, repository fetching, entrypoint detection
- **`iac_wrapper/dockerize.py`**: Docker image building and container management
- **`iac_wrapper/envoy.py`**: Envoy sidecar configuration and certificate management
- **`iac_wrapper/api.py`**: Flask admin API with Supabase JWT authentication
- **`iac_wrapper/cli.py`**: Click-based CLI interface
- **`iac_wrapper/controlplane.py`**: gRPC client for service health checks
- **`proto/controlplane.proto`**: gRPC service definitions
- **`infra/`**: Terraform configuration for Docker resources

### Key Files

- **`pyproject.toml`**: Python project configuration with dependencies and CLI entry point
- **`Makefile`**: Development workflow automation
- **`repos.yaml`**: Example repository slugs for deployment
- **`.pre-commit-config.yaml`**: Code quality hooks (black, flake8, mypy)
- **`requirements.txt`**: Python dependencies

### Network and Security

- All services run on Docker network `iacnet` (172.20.0.0/16)
- mTLS between services using self-signed CA (development) at `./secrets/`
- Envoy sidecars handle service mesh (port 15000 inbound, 15001 outbound, 9901 metrics)
- Applications use gRPC on port 50051
- Flask admin API on 127.0.0.1:8080 + Unix domain socket `/run/iac_wrapper.sock`

### Environment Configuration

Required environment variables in `.env`:
- `SUPABASE_URL`: Supabase project URL for JWT validation
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key for authentication
- `OTEL_EXPORTER_OTLP_ENDPOINT` (optional): OpenTelemetry collector endpoint

## Testing

- Uses pytest with coverage requirements (80% minimum)
- Integration tests use testcontainers for ephemeral Docker environments
- Test markers: `slow`, `integration`
- Run specific test types: `pytest -m "not slow"` or `pytest -m integration`

## Development Notes

- Python 3.11+ required
- Pre-commit hooks enforce code quality (black, flake8, mypy)
- Protobuf files auto-generated in `iac_wrapper/grpc_pb/` (don't edit manually)
- Repository cache stored in system temp directory under `iac_wrapper_cache`
- Self-signed certificates for development only - see README for production PKI setup
