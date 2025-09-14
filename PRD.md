SYSTEM
You are a senior platform engineer. Build production-grade, testable code with strong defaults and zero fluff.

USER
Goal
Create an Infrastructure-as-Code (IaC) “deployment wrapper” that, given a list of git repository slugs, stands up containerized runtimes for each and executes the fetched project’s `main()` function. The solution must be deterministic, test-driven, and runnable on a fresh machine with Docker installed.

Tech/Architecture (must use)
- IaC: Terraform (Docker provider) for declarative container/network resources.
- Orchestration: Python CLI + Flask admin API (thin control plane).
- Containers: Docker, one container per repo + an Envoy sidecar per service.
- AuthN: Supabase Auth (service role JWT) protecting the Flask admin API (call Supabase to validate).
- Internal comms: gRPC + protobuf between control plane and services (basic Health + Logs RPC).
- mTLS & observability: Envoy sidecar per service for gRPC mTLS and metrics; OpenTelemetry in Python apps; stdout logs.
- Sockets: Flask admin also exposes a Unix domain socket for local rootless control.
- Language/tooling: Python 3.11, Flask, pytest, black.
- TDD: write tests first or alongside; include fixtures and integration tests using ephemeral containers.

What to build (deliverables)
1) Repo layout
   .
   ├── Makefile
   ├── README.md
   ├── .env.example
   ├── pyproject.toml
   ├── requirements.txt
   ├── pre-commit-config.yaml
   ├── proto/
   │   └── controlplane.proto          # HealthCheck, LogsStream, DeployRequest/Result
   ├── infra/
   │   ├── main.tf                     # terraform { required_providers { docker } }
   │   ├── variables.tf
   │   ├── outputs.tf
   │   └── templates/
   │       ├── envoy.yaml.tmpl         # per-service mTLS + stats/prom endpoints
   │       └── app.Dockerfile.tmpl     # base runner image
   ├── iac_wrapper/
   │   ├── __init__.py
   │   ├── config.py                   # env loading, paths, defaults
   │   ├── auth.py                     # Supabase JWT validation
   │   ├── slug.py                     # parse slugs: gh:owner/repo[#ref]
   │   ├── gitops.py                   # shallow clone or archive fetch
   │   ├── dockerize.py                # build image, tag, push local, compose env
   │   ├── envoy.py                    # render sidecar config, issue certs (self-signed dev CA)
   │   ├── grpc_pb/                    # generated from proto
   │   ├── controlplane.py             # gRPC client to talk to services
   │   ├── api.py                      # Flask admin API (HTTP + UDS)
   │   └── cli.py                      # click/argparse CLI entry
   └── tests/
       ├── conftest.py
       ├── test_slug.py
       ├── test_gitops.py
       ├── test_dockerize.py
       ├── test_api_auth.py
       └── test_integration_deploy.py  # spins a container and asserts HealthCheck

2) Behavior
   - Input: a YAML/JSON list of repo slugs, e.g.:
       gh:openai/sample-app#v1.2.3
       gh:org/service-a
     Slug format: scheme ("gh"), owner/repo, optional #ref (branch|tag|sha).
   - For each slug:
     a) Fetch source (prefer tarball at ref; fallback to shallow clone).
     b) Detect Python entry:
        - If package has `__main__.py` or `main.py` at root, run that.
        - If pyproject has `[project.scripts]`, choose the first console script as entry.
        - Else look for `{package}/__main__.py`.
     c) Build a Docker image from `infra/templates/app.Dockerfile.tmpl`:
        - Base: python:3.11-slim
        - Install app into /app, create nonroot user, expose gRPC port (default 50051)
        - Run under `python -m PACKAGE` or `python /app/main.py`
        - Add OpenTelemetry SDK; export OTLP to stdout by default.
     d) Generate an Envoy sidecar config with:
        - mTLS between sidecars (self-signed CA generated at bootstrap; per-service leaf certs)
        - HTTP admin disabled; metrics on 9901 bound to localhost only
        - gRPC pass-through to app on 50051 with ALPN h2 and strict TLS
     e) Terraform resources (docker provider):
        - docker_network for the stack
        - docker_image for app and envoy
        - docker_container app + docker_container envoy (shared network, mounted certs)
     f) After apply, call the service HealthCheck via the control plane over mTLS (through Envoy).
   - Flask admin API:
     - POST /deploy { slugs: [...] } -> async-ish apply with streaming logs
     - GET /health -> control plane health
     - Auth: Requires `Authorization: Bearer <JWT>` validated against Supabase (service role key and URL via env).
     - Socket: also bind on UDS path `/run/iac_wrapper.sock` for local automation.
   - CLI:
     - `iac deploy --file repos.yaml`
     - `iac plan`
     - `iac destroy`
     - `iac health`

3) Security/keys
   - `.env` keys: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OTEL_EXPORTER_OTLP_ENDPOINT (optional).
   - Generate a local dev CA at `./secrets/ca.{pem,key}`; issue leaf certs per service (SAN = service DNS on docker network).
   - Never commit secrets; include .gitignore.

4) Tests (pytest)
   - Unit tests for slug parsing, git fetch, Dockerfile render, envoy config render, Supabase JWT path (mock HTTP).
   - Integration test using testcontainers or docker SDK:
     - Build a sample “hello-main” repo fixture on the fly.
     - Deploy via CLI to a random project name and assert HealthCheck returns SERVING.
   - Include `pytest.ini` and coverage config. Use tmp paths. Keep tests under 90s total.

5) Tooling & quality
   - `black` formatting, pre-commit hooks for black and basic lint.
   - Makefile targets:
       make bootstrap   # create venv, install deps, pre-commit install, generate proto
       make proto       # compile protobufs to iac_wrapper/grpc_pb
       make plan/apply/destroy
       make test
       make fmt
   - `requirements.txt` minimal: flask, requests, python-dotenv, grpcio, grpcio-tools, cryptography, jinja2, docker, pydantic, click, opentelemetry-sdk, opentelemetry-exporter-otlp, pytest, testcontainers[compose] (if used).

6) Protobuf (controlplane.proto)
   - services:
       rpc HealthCheck(google.protobuf.Empty) returns (HealthStatus);
       rpc StreamLogs(LogRequest) returns (stream LogLine);
       rpc Deploy(DeployRequest) returns (DeployResult);
   - messages: HealthStatus { enum status }, LogRequest { service }, LogLine { ts, msg }, DeployRequest { repeated string slugs }, DeployResult { repeated ServiceResult }.

7) README.md must include
   - One-command quickstart:
       cp .env.example .env
       make bootstrap
       make plan && make apply
       iac deploy --file repos.yaml
   - Explainer: how slug detection works; how `main()` is resolved; how to override entrypoint with `ENTRYPOINT` label.
   - Observability: how to view envoy stats, app logs, and set OTLP endpoint.
   - Limitations and how to swap self-signed CA for a real PKI later.

8) Opinionated defaults (do this unless overridden)
   - Everything runs on a single docker network named `iacnet`.
   - gRPC port 50051 per service; Envoy listens 15000 inbound, 15001 outbound, metrics on 9901 (localhost).
   - Unix domain socket for admin API at `/run/iac_wrapper.sock` plus HTTP on 127.0.0.1:8080.
   - If repo is non-Python, still run by executing `/app/main` if present; otherwise fail with a clear error.

9) Output now
   - Full code for all files listed above.
   - Example `repos.yaml` with two public slugs (use small sample repos).
   - Example `envoy.yaml.tmpl` and the Python CA issuance helper.
   - Tests and a green `pytest -q` run transcript for the happy path.
   - No TODOs. No placeholders. Working defaults.

Non-goals
- No Kubernetes. Keep it Docker + Terraform for clarity.
- No database; Supabase used only for JWT validation of admin endpoints.
- No long-running background workers; the control plane triggers Terraform and polls.
