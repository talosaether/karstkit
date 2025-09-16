# End-to-End Deployment Pipeline Test

This document describes the comprehensive end-to-end integration test for the KarstKit deployment pipeline, specifically designed to validate the complete deployment workflow for `gh:talosaether/dshbrd` before release.

## Overview

The end-to-end test validates the entire deployment pipeline from repository deployment to service health verification. It serves as a final check in the CI/CD pipeline before release.

### Test Workflow

```
cd karstkit && source venv/bin/activate
↓
iac deploy --file repos.yaml --wait --timeout 180
↓
Comprehensive health checks on deployed services
↓
Service mesh connectivity verification
↓
Application-specific endpoint testing
↓
Resource cleanup
```

## Files

- **`test_e2e_deployment_pipeline.py`** - Main test script
- **`.github/workflows/e2e-deployment-test.yml`** - GitHub Actions CI/CD pipeline
- **`karstkit/Makefile`** - Added `e2e-test` targets for local execution

## Running the Test

### Local Execution

```bash
# From the karstkit directory
make e2e-test

# Or directly
cd karstkit && source venv/bin/activate
cd .. && python test_e2e_deployment_pipeline.py
```

### CI/CD Pipeline

The test runs automatically on:
- Push to `main` or `develop` branches
- Pull requests to `main`
- Daily at 2 AM UTC (scheduled)
- Manual trigger via GitHub Actions UI

## Test Phases

### 1. Prerequisites Check ✓
- Verifies KarstKit directory structure
- Checks for `repos.yaml` configuration
- Validates virtual environment setup
- Confirms Docker availability

### 2. Deployment ✓
- Activates KarstKit virtual environment
- Executes `iac deploy --file repos.yaml --wait --timeout 180`
- Monitors deployment progress and output

### 3. Service Discovery ✓
- Discovers deployed containers
- Identifies IAC-managed services
- Maps service names and container IDs

### 4. Health Checks ✓
- Runs `iac health` command for each service
- Validates service responsiveness
- Checks gRPC health endpoints

### 5. dshbrd Specific Testing ✓
- Tests HTTP endpoints (`/healthz`, `/readyz`, `/`)
- Validates JSON response format
- Checks service-specific functionality

### 6. Service Mesh Validation ✓
- Verifies Envoy sidecar containers
- Tests mTLS configuration
- Validates service mesh connectivity

### 7. Application Tests ✓
- Runs existing dshbrd test suite
- Validates application functionality
- Ensures integration compatibility

### 8. Cleanup ✓
- Executes `iac destroy --yes`
- Removes Docker containers and images
- Cleans up test resources

## Test Configuration

### Environment Variables

- `TEST_TIMEOUT` - Maximum test execution time (default: 300s)

### Timeouts

- Overall test: 300 seconds (5 minutes)
- Deployment: 200 seconds
- Health checks: 30 seconds per service
- Cleanup: 120 seconds

### Expected Services

The test expects to deploy and validate:
- `gh:talosaether/dshbrd` - Main dashboard application
- Associated Envoy sidecars for service mesh

## Success Criteria

For the test to pass, all of the following must succeed:

1. ✅ Prerequisites validation
2. ✅ Successful deployment of all services
3. ✅ All health checks return healthy status
4. ✅ dshbrd HTTP endpoints respond correctly
5. ✅ Service mesh components are functional
6. ✅ Application test suite passes
7. ✅ Clean resource cleanup

## Failure Scenarios

The test will fail if:

- ❌ Docker is not available
- ❌ KarstKit environment is not properly set up
- ❌ Deployment times out or fails
- ❌ Any service fails health checks
- ❌ HTTP endpoints return non-200 status codes
- ❌ Service mesh connectivity issues
- ❌ Application tests fail
- ❌ Resource cleanup fails

## Debugging Failed Tests

### Local Debugging

```bash
# Run with verbose output
python test_e2e_deployment_pipeline.py

# Check Docker containers
docker ps -a

# Check KarstKit logs
cd karstkit && source venv/bin/activate
iac logs

# Manual health check
iac health
```

### CI/CD Debugging

1. **Download test artifacts** from GitHub Actions
2. **Review container logs** in `artifacts/logs/`
3. **Check deployment configuration** in `artifacts/configs/`
4. **Analyze system information** in `artifacts/logs/system-info.log`

### Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| Docker not available | "Docker not available" error | Ensure Docker daemon is running |
| Deployment timeout | "Deployment failed" after 200s | Check network connectivity, increase timeout |
| Port conflicts | Service startup failures | Ensure no other services using target ports |
| Resource exhaustion | Container start failures | Free up disk space, memory |
| Network issues | Service mesh connectivity failures | Check Docker network configuration |

## Integration with CI/CD

### GitHub Actions Integration

The pipeline automatically:
- Sets up Python and Docker environments
- Caches dependencies for faster execution
- Collects comprehensive logs and artifacts
- Provides detailed test summaries
- Performs automatic cleanup

### Release Gating

This test serves as a **release gate** - deployments should only proceed to production if this end-to-end test passes completely.

### Monitoring

- **Daily scheduled runs** catch regressions
- **Artifact retention** (7 days) for debugging
- **Slack/email notifications** on failures (configure in repo settings)

## Development Notes

### Adding New Test Scenarios

To add new test scenarios:

1. Add new methods to `E2EDeploymentTest` class
2. Call them in `run_complete_test()` method
3. Update success criteria documentation
4. Test locally before committing

### Extending for Additional Services

To test additional services beyond dshbrd:

1. Update `repos.yaml` with new service entries
2. Add service-specific test methods
3. Update expected service discovery logic
4. Add service-specific endpoint tests

### Performance Optimization

- **Parallel health checks** for multiple services
- **Container reuse** for faster test cycles
- **Cached base images** to reduce build time
- **Incremental cleanup** to avoid resource conflicts

## Security Considerations

- Uses temporary Docker networks for isolation
- Cleans up all resources after testing
- No persistent data storage during tests
- Secure handling of service mesh certificates

## Support

For issues with the end-to-end test:

1. Check this documentation
2. Review test logs and artifacts
3. Validate local environment setup
4. Create GitHub issue with test artifacts attached

---

**Last Updated**: Generated for KarstKit deployment pipeline testing
**Test Version**: 1.0.0
**Supported Platforms**: Linux (Ubuntu 20.04+), macOS (with Docker)
