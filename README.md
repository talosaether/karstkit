# KarstKit

An Infrastructure-as-Code (IaC) deployment wrapper that spelunks repository slugs, spins up Dockerized services with mTLS, and executes Python applications in a secure service mesh.

## 🚀 Quick Start

### Prerequisites (Ubuntu/Debian)

Install build dependencies to avoid cryptography compilation issues:

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y build-essential libssl-dev libffi-dev python3-dev
```

### Setup and Deployment

```bash
# One-command setup and deployment
cp env.example .env
make bootstrap
source venv/bin/activate
make plan && make apply
iac deploy --file repos.yaml
```

## 📋 How It Works

### Repository Slug Detection

KarstKit supports multiple repository formats:
- `gh:owner/repo` - GitHub repository
- `gh:owner/repo#branch` - Specific branch or tag
- `gl:owner/repo` - GitLab repository
- `bb:owner/repo` - Bitbucket repository

The system automatically detects the repository type and fetches the source code using the most efficient method (tarball download preferred, shallow clone fallback).

### Main() Function Resolution

KarstKit intelligently detects Python entrypoints in this order:

1. **Console Scripts**: Checks `pyproject.toml` for `[project.scripts]` and uses the first one
2. **Package Main**: Looks for `{package}/__main__.py`
3. **Root Main**: Searches for `main.py` or `__main__.py` at repository root
4. **App Structure**: Detects `app.py`, `app/__main__.py`, or `src/{package}/__main__.py`
5. **Function Detection**: Scans Python files for `def main(` or `if __name__ == "__main__"`

### Overriding Entrypoints

You can override the detected entrypoint using Docker labels:

```dockerfile
# In your Dockerfile
LABEL ENTRYPOINT="custom.module:main_function"
```

Or via environment variable:
```bash
export ENTRYPOINT="myapp.cli:start"
```

## 📊 Observability

### Envoy Statistics

View Envoy metrics and statistics:
```bash
# Access Envoy admin interface (per service)
curl http://localhost:9901/stats

# View service-specific metrics
curl http://localhost:9901/stats?filter=service_name
```

### Application Logs

Stream logs from deployed services:
```bash
# Stream all service logs
iac logs

# Stream specific service logs
iac logs --service my-service

# Follow logs in real-time
iac logs --follow
```

### OpenTelemetry Configuration

Set custom OTLP endpoint for distributed tracing:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://your-otel-collector:4317"
export OTEL_SERVICE_NAME="karstkit-service"
```

View traces in your OpenTelemetry-compatible backend (Jaeger, Zipkin, etc.).

## 🔒 Security & PKI

### Current: Self-Signed CA

KarstKit generates a development CA automatically:
- CA certificate: `./secrets/ca.pem`
- CA private key: `./secrets/ca.key`
- Service certificates: `./secrets/{service-name}.{crt,key}`

### Production: Real PKI Integration

To replace the self-signed CA with a production PKI:

1. **Replace CA files**:
   ```bash
   # Copy your CA certificate and key
   cp /path/to/prod-ca.pem ./secrets/ca.pem
   cp /path/to/prod-ca.key ./secrets/ca.key
   ```

2. **Update certificate generation** in `iac_wrapper/envoy.py`:
   ```python
   # Modify the certificate generation logic to use your PKI
   # instead of the self-signed CA generation
   ```

3. **Configure service certificates**:
   - Ensure each service has a valid certificate from your PKI
   - Update the certificate paths in Envoy configuration
   - Verify certificate chain and trust relationships

## ⚠️ Limitations

- **Single Docker Network**: All services run on the `iacnet` network
- **Development CA**: Default self-signed certificates for development only
- **Local Storage**: Repository cache and certificates stored locally
- **No High Availability**: Single control plane instance
- **Python Focus**: Optimized for Python applications (other languages supported via `/app/main`)

## 🛠️ Architecture

KarstKit is built with a modular, test-driven architecture:

### Core Components

- **Python CLI + Flask API**: Thin control plane for orchestration
- **Terraform**: Declarative infrastructure using Docker provider
- **Envoy Sidecars**: mTLS service mesh for secure inter-service communication
- **gRPC + Protobuf**: Type-safe communication between services
- **OpenTelemetry**: Built-in observability and distributed tracing

### Repository Structure

```
.
├── Makefile                        # Development workflow automation
├── README.md                       # This file
├── CLAUDE.md                      # Development guide for Claude Code
├── .env.example                   # Environment template
├── pyproject.toml                 # Python project configuration
├── requirements.txt               # Python dependencies
├── .pre-commit-config.yaml       # Code quality hooks
├── repos.yaml                     # Example repository configuration
├── proto/
│   └── controlplane.proto         # gRPC service definitions
├── infra/
│   ├── main.tf                    # Terraform Docker resources
│   ├── variables.tf               # Terraform variables
│   ├── outputs.tf                 # Terraform outputs
│   └── templates/
│       ├── envoy.yaml.tmpl        # Envoy sidecar configuration
│       └── app.Dockerfile.tmpl    # Application container template
├── iac_wrapper/
│   ├── config.py                  # Configuration and environment handling
│   ├── auth.py                    # Supabase JWT authentication
│   ├── slug.py                    # Repository slug parsing
│   ├── gitops.py                  # Git operations and entrypoint detection
│   ├── dockerize.py               # Docker image building and management
│   ├── envoy.py                   # Envoy configuration and certificate management
│   ├── grpc_pb/                   # Generated protobuf code
│   ├── controlplane.py            # gRPC client for service communication
│   ├── api.py                     # Flask admin API
│   └── cli.py                     # Command-line interface
└── tests/
    ├── conftest.py                       # Pytest fixtures and configuration
    ├── test_*.py                         # Comprehensive test suite (131+ tests)
    ├── test_integration_deploy.py        # End-to-end deployment tests
    ├── test_e2e_deployment_pipeline.py   # Complete E2E pipeline validation
    └── E2E_DEPLOYMENT_TEST.md            # E2E test documentation
```

### Service Mesh Architecture

- **Docker Network**: Single `iacnet` bridge network (172.20.0.0/16)
- **Service Communication**: gRPC on port 50051 per service
- **Envoy Ports**: 15000 (inbound), 15001 (outbound), 9901 (metrics)
- **mTLS Certificates**: Self-signed CA with per-service leaf certificates
- **Admin API**: HTTP on 127.0.0.1:8080 + Unix domain socket at `/run/iac_wrapper.sock`

## 🧪 Testing & Quality

KarstKit includes a comprehensive test suite ensuring reliability and maintainability:

### Test Coverage

- **131+ Tests** across all components
- **Unit Tests**: Slug parsing, Git operations, Docker management, authentication
- **Integration Tests**: Full deployment workflows with health checks
- **Mocking**: Comprehensive external dependency mocking
- **Coverage Target**: 80% minimum coverage requirement

### Test Structure

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov

# Run specific test categories
pytest -m "not slow"              # Skip slow tests
pytest -m integration             # Integration tests only
pytest tests/test_slug.py -v      # Specific component tests

# Run end-to-end deployment pipeline test
make e2e-test                     # Complete deployment validation
```

### Quality Tools

- **Black**: Code formatting (88 character line length)
- **Pre-commit**: Automated code quality checks
- **MyPy**: Static type checking
- **Pytest**: Testing framework with coverage reporting

## 🚀 Development Workflow

### Common Commands

```bash
# Setup development environment
make bootstrap

# Generate protobuf files
make proto

# Format code
make fmt

# Run linting
make lint

# Run tests
make test

# Run end-to-end deployment test
make e2e-test

# Infrastructure commands
make plan          # Show Terraform plan
make apply         # Apply infrastructure changes
make destroy       # Destroy all resources
```

### Adding New Components

1. **Create the module** in `iac_wrapper/`
2. **Write tests first** in `tests/test_<component>.py`
3. **Implement functionality** following existing patterns
4. **Update documentation** as needed
5. **Run quality checks** with `make fmt lint test`

## 🔧 Configuration

### Environment Variables

Required in `.env` file:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317  # Optional
```

### Default Ports

- **gRPC Services**: 50051
- **Envoy Inbound**: 15000
- **Envoy Outbound**: 15001
- **Envoy Metrics**: 9901
- **Admin API**: 8080

## 🔄 CI/CD Pipeline

KarstKit includes automated testing and deployment validation:

### GitHub Actions Workflows

- **End-to-End Deployment Test**: Validates complete deployment pipeline
  - Runs on pushes to main/develop branches
  - Daily scheduled runs to catch regressions
  - Tests full deployment workflow for `gh:talosaether/dshbrd`
  - Validates service mesh, health checks, and cleanup

### Running CI/CD Locally

```bash
# Run the same E2E test that runs in CI
make e2e-test

# Run with CI-friendly output
make e2e-test-ci
```

## 📚 Documentation

- **`CLAUDE.md`**: Comprehensive development guide for AI code assistants
- **`README.md`**: This overview and usage guide
- **`tests/E2E_DEPLOYMENT_TEST.md`**: Complete E2E testing documentation
- **Inline Documentation**: Extensive docstrings and type hints throughout codebase
- **Test Examples**: Tests serve as living documentation of component behavior
