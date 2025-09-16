#!/usr/bin/env python3
"""
End-to-End Integration Test for KarstKit Deployment Pipeline

This test validates the complete deployment pipeline from repository
deployment to service health verification for gh:talosaether/dshbrd.

Usage:
    python test_e2e_deployment_pipeline.py

Expected workflow:
1. cd karstkit && source venv/bin/activate
2. iac deploy --file repos.yaml --wait --timeout 180
3. Run comprehensive health checks on deployed services
4. Verify service mesh connectivity
5. Clean up resources

This test is designed to be run as a final CI/CD check before release.
"""

import os
import sys
import subprocess
import time
import json
import requests
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class E2EDeploymentTest:
    """End-to-end deployment test orchestrator."""

    def __init__(self, test_timeout: int = 300):
        self.test_timeout = test_timeout
        self.karstkit_dir = Path(
            __file__
        ).parent.parent  # Go up from tests/ to karstkit/
        self.repos_yaml = self.karstkit_dir / "repos.yaml"
        self.venv_path = self.karstkit_dir / "venv"
        self.deployed_services: List[str] = []
        self.start_time = time.time()

    def log_progress(self, message: str, level: str = "INFO"):
        """Log progress with timestamp."""
        elapsed = time.time() - self.start_time
        if level == "ERROR":
            logger.error(f"[{elapsed:.1f}s] {message}")
        elif level == "WARNING":
            logger.warning(f"[{elapsed:.1f}s] {message}")
        else:
            logger.info(f"[{elapsed:.1f}s] {message}")

    def run_command(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        timeout: int = 60,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run command with logging and error handling."""
        cmd_str = " ".join(cmd)
        self.log_progress(f"Running: {cmd_str}")

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.karstkit_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )

            if result.stdout:
                self.log_progress(f"STDOUT: {result.stdout.strip()}")
            if result.stderr:
                self.log_progress(f"STDERR: {result.stderr.strip()}", "WARNING")

            return result

        except subprocess.TimeoutExpired:
            self.log_progress(f"Command timed out after {timeout}s: {cmd_str}", "ERROR")
            raise
        except subprocess.CalledProcessError as e:
            self.log_progress(
                f"Command failed with exit code {e.returncode}: {cmd_str}", "ERROR"
            )
            if e.stdout:
                self.log_progress(f"Failed STDOUT: {e.stdout.strip()}", "ERROR")
            if e.stderr:
                self.log_progress(f"Failed STDERR: {e.stderr.strip()}", "ERROR")
            raise

    def check_prerequisites(self) -> bool:
        """Verify all prerequisites are met."""
        self.log_progress("🔍 Checking prerequisites...")

        # Check karstkit directory exists
        if not self.karstkit_dir.exists():
            self.log_progress(
                f"KarstKit directory not found: {self.karstkit_dir}", "ERROR"
            )
            return False

        # Check repos.yaml exists
        if not self.repos_yaml.exists():
            self.log_progress(f"repos.yaml not found: {self.repos_yaml}", "ERROR")
            return False

        # Check virtual environment exists
        if not self.venv_path.exists():
            self.log_progress(
                f"Virtual environment not found: {self.venv_path}", "ERROR"
            )
            return False

        # Check Docker is available
        try:
            self.run_command(["docker", "--version"], timeout=10)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.log_progress("Docker not available", "ERROR")
            return False

        self.log_progress("✅ Prerequisites check passed")
        return True

    def activate_venv_and_deploy(self) -> bool:
        """Activate virtual environment and deploy services."""
        self.log_progress("🚀 Starting deployment...")

        # Create activation script that sources venv and runs deployment
        activation_script = f"""
        set -e
        cd {self.karstkit_dir}
        source venv/bin/activate
        iac deploy --file repos.yaml --wait --timeout 180
        """

        try:
            # Write script to temporary file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(activation_script)
                script_path = f.name

            # Make script executable
            os.chmod(script_path, 0o755)

            # Run the deployment script
            result = self.run_command(
                ["bash", script_path],
                timeout=200,  # Extended timeout for deployment
                check=False,
            )

            # Clean up script
            os.unlink(script_path)

            if result.returncode != 0:
                self.log_progress("Deployment failed", "ERROR")
                return False

            self.log_progress("✅ Deployment completed successfully")
            return True

        except Exception as e:
            self.log_progress(f"Deployment error: {e}", "ERROR")
            return False

    def discover_deployed_services(self) -> List[str]:
        """Discover what services were deployed."""
        self.log_progress("🔍 Discovering deployed services...")

        try:
            # Get list of running containers
            result = self.run_command(
                ["docker", "ps", "--format", "{{.Names}}"], check=False
            )
            if result.returncode != 0:
                return []

            containers = (
                result.stdout.strip().split("\n") if result.stdout.strip() else []
            )

            # Filter for IAC-related containers
            services = []
            for container in containers:
                if container.startswith("iac-") and not container.endswith("-envoy"):
                    service_name = container.replace("iac-", "").replace("-", "_")
                    services.append(service_name)

            self.deployed_services = services
            self.log_progress(f"Discovered services: {services}")
            return services

        except Exception as e:
            self.log_progress(f"Service discovery error: {e}", "ERROR")
            return []

    def check_service_health(self, service_name: str) -> bool:
        """Check health of a specific service."""
        self.log_progress(f"🏥 Checking health of service: {service_name}")

        # Use IAC health check command
        health_script = f"""
        set -e
        cd {self.karstkit_dir}
        source venv/bin/activate
        iac health
        """

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(health_script)
                script_path = f.name

            os.chmod(script_path, 0o755)

            result = self.run_command(["bash", script_path], timeout=30, check=False)

            os.unlink(script_path)

            if result.returncode == 0:
                self.log_progress(f"✅ Service {service_name} is healthy")
                return True
            else:
                self.log_progress(
                    f"❌ Service {service_name} health check failed", "WARNING"
                )
                return False

        except Exception as e:
            self.log_progress(f"Health check error for {service_name}: {e}", "ERROR")
            return False

    def test_dshbrd_specific_endpoints(self) -> bool:
        """Test specific endpoints for the dshbrd service."""
        self.log_progress("🎯 Testing dshbrd specific endpoints...")

        # Try to find the dshbrd container port mapping
        try:
            result = self.run_command(["docker", "port", "iac-dshbrd"], check=False)

            if result.returncode != 0:
                self.log_progress(
                    "Could not find dshbrd container port mapping", "WARNING"
                )
                return False

            # Parse port mapping (e.g., "5000/tcp -> 0.0.0.0:32768")
            port_info = result.stdout.strip()
            if not port_info:
                self.log_progress("No port mapping found for dshbrd", "WARNING")
                return False

            # Extract the mapped port
            try:
                mapped_port = port_info.split("->")[1].strip().split(":")[1]
                base_url = f"http://localhost:{mapped_port}"

                # Test health endpoints
                endpoints_to_test = ["/healthz", "/readyz", "/"]  # main page

                all_passed = True
                for endpoint in endpoints_to_test:
                    try:
                        self.log_progress(f"Testing endpoint: {base_url}{endpoint}")
                        response = requests.get(f"{base_url}{endpoint}", timeout=10)

                        if response.status_code == 200:
                            self.log_progress(f"✅ {endpoint} responded with 200")
                        else:
                            self.log_progress(
                                f"❌ {endpoint} responded with {response.status_code}",
                                "WARNING",
                            )
                            all_passed = False

                    except requests.RequestException as e:
                        self.log_progress(f"❌ {endpoint} failed: {e}", "WARNING")
                        all_passed = False

                return all_passed

            except (IndexError, ValueError) as e:
                self.log_progress(f"Could not parse port mapping: {e}", "WARNING")
                return False

        except Exception as e:
            self.log_progress(f"Error testing dshbrd endpoints: {e}", "ERROR")
            return False

    def test_service_mesh_connectivity(self) -> bool:
        """Test service mesh connectivity between services."""
        self.log_progress("🕸️ Testing service mesh connectivity...")

        try:
            # Check if envoy containers are running
            result = self.run_command(
                ["docker", "ps", "--filter", "name=envoy", "--format", "{{.Names}}"],
                check=False,
            )

            if result.returncode != 0:
                self.log_progress("Could not check envoy containers", "WARNING")
                return False

            envoy_containers = (
                result.stdout.strip().split("\n") if result.stdout.strip() else []
            )

            if not envoy_containers:
                self.log_progress("No envoy containers found", "WARNING")
                return False

            self.log_progress(f"Found envoy containers: {envoy_containers}")

            # Test envoy admin interface for each container
            all_healthy = True
            for container in envoy_containers:
                if not container:
                    continue

                try:
                    # Check envoy admin port (usually 9901)
                    port_result = self.run_command(
                        ["docker", "port", container], check=False
                    )

                    if port_result.returncode == 0 and "9901" in port_result.stdout:
                        self.log_progress(
                            f"✅ Envoy {container} admin interface available"
                        )
                    else:
                        self.log_progress(
                            f"❌ Envoy {container} admin interface not accessible",
                            "WARNING",
                        )
                        all_healthy = False

                except Exception as e:
                    self.log_progress(
                        f"Error checking envoy {container}: {e}", "WARNING"
                    )
                    all_healthy = False

            return all_healthy

        except Exception as e:
            self.log_progress(f"Service mesh connectivity test error: {e}", "ERROR")
            return False

    def run_dshbrd_tests(self) -> bool:
        """Run the existing dshbrd test suite."""
        self.log_progress("🧪 Running dshbrd test suite...")

        dshbrd_dir = (
            Path(__file__).parent.parent.parent / "dshbrd"
        )  # Go up from tests/karstkit/repos/ to repos/dshbrd
        if not dshbrd_dir.exists():
            self.log_progress("dshbrd directory not found", "WARNING")
            return False

        try:
            # Activate dshbrd venv and run tests
            test_script = f"""
            set -e
            cd {dshbrd_dir}
            if [ -d "venv" ]; then
                source venv/bin/activate
            fi
            python -m pytest tests/ -v
            """

            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(test_script)
                script_path = f.name

            os.chmod(script_path, 0o755)

            result = self.run_command(["bash", script_path], timeout=60, check=False)

            os.unlink(script_path)

            if result.returncode == 0:
                self.log_progress("✅ dshbrd tests passed")
                return True
            else:
                self.log_progress("❌ dshbrd tests failed", "WARNING")
                return False

        except Exception as e:
            self.log_progress(f"Error running dshbrd tests: {e}", "ERROR")
            return False

    def cleanup_resources(self) -> bool:
        """Clean up deployed resources."""
        self.log_progress("🧹 Cleaning up resources...")

        cleanup_script = f"""
        set -e
        cd {self.karstkit_dir}
        source venv/bin/activate
        iac destroy --yes
        """

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(cleanup_script)
                script_path = f.name

            os.chmod(script_path, 0o755)

            result = self.run_command(
                ["bash", script_path],
                timeout=120,  # Extended timeout for cleanup
                check=False,
            )

            os.unlink(script_path)

            if result.returncode == 0:
                self.log_progress("✅ Resources cleaned up successfully")
                return True
            else:
                self.log_progress("❌ Cleanup failed", "WARNING")
                return False

        except Exception as e:
            self.log_progress(f"Cleanup error: {e}", "ERROR")
            return False

    def run_complete_test(self) -> bool:
        """Run the complete end-to-end test."""
        self.log_progress("🚀 Starting End-to-End Deployment Pipeline Test")
        self.log_progress("=" * 60)

        success = True

        try:
            # Phase 1: Prerequisites
            if not self.check_prerequisites():
                return False

            # Phase 2: Deployment
            if not self.activate_venv_and_deploy():
                return False

            # Phase 3: Service Discovery
            services = self.discover_deployed_services()
            if not services:
                self.log_progress("No services discovered", "WARNING")
                success = False

            # Phase 4: Health Checks
            for service in services:
                if not self.check_service_health(service):
                    success = False

            # Phase 5: dshbrd Specific Tests
            if not self.test_dshbrd_specific_endpoints():
                success = False

            # Phase 6: Service Mesh Tests
            if not self.test_service_mesh_connectivity():
                success = False

            # Phase 7: Application Tests
            if not self.run_dshbrd_tests():
                success = False

        except Exception as e:
            self.log_progress(f"Test execution error: {e}", "ERROR")
            success = False

        finally:
            # Always attempt cleanup
            self.cleanup_resources()

        # Final report
        elapsed = time.time() - self.start_time
        self.log_progress("=" * 60)

        if success:
            self.log_progress(f"🎉 END-TO-END TEST PASSED in {elapsed:.1f}s")
            self.log_progress("✅ All deployment pipeline components working correctly")
            return True
        else:
            self.log_progress(f"❌ END-TO-END TEST FAILED in {elapsed:.1f}s")
            self.log_progress("💡 Check logs above for specific failure details")
            return False


def main():
    """Main entry point for the test."""
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        return 0

    test = E2EDeploymentTest(test_timeout=300)

    if test.run_complete_test():
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
