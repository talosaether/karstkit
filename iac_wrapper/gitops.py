"""Git operations for fetching repositories."""

import os
import tarfile
import tempfile
import requests
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from .slug import RepoSlug


class GitOps:
    """Git operations handler."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "iac_wrapper_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_repo(self, slug: RepoSlug) -> Path:
        """Fetch a repository from the given slug.

        Args:
            slug: Repository slug to fetch

        Returns:
            Path to the fetched repository

        Raises:
            RuntimeError: If fetching fails
        """
        # Try archive download first (faster)
        try:
            return self._fetch_archive(slug)
        except Exception as e:
            # Fallback to shallow clone
            try:
                return self._fetch_clone(slug)
            except Exception as clone_error:
                raise RuntimeError(
                    f"Failed to fetch repository {slug}: {e}, clone failed: {clone_error}"
                )

    def _fetch_archive(self, slug: RepoSlug) -> Path:
        """Fetch repository using archive download."""
        archive_url = slug.archive_url
        response = requests.get(archive_url, stream=True)
        response.raise_for_status()

        # Create temporary directory for extraction
        extract_dir = self.cache_dir / f"{slug.service_name}-{slug.ref or 'main'}"
        if extract_dir.exists():
            return extract_dir

        extract_dir.mkdir(parents=True, exist_ok=True)

        # Download and extract archive
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file.flush()

            # Extract the archive
            with tarfile.open(temp_file.name, "r:gz") as tar:
                # Get the root directory name
                members = tar.getmembers()
                if members:
                    root_dir = members[0].name.split("/")[0]
                    tar.extractall(extract_dir)

                    # Move contents from subdirectory to root
                    subdir = extract_dir / root_dir
                    if subdir.exists():
                        for item in subdir.iterdir():
                            item.rename(extract_dir / item.name)
                        subdir.rmdir()

            # Clean up temporary file
            os.unlink(temp_file.name)

        return extract_dir

    def _fetch_clone(self, slug: RepoSlug) -> Path:
        """Fetch repository using shallow clone."""
        clone_dir = self.cache_dir / slug.service_name
        if clone_dir.exists():
            return clone_dir

        clone_dir.mkdir(parents=True, exist_ok=True)

        # Perform shallow clone
        cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--branch",
            slug.ref or "main",
            slug.clone_url,
            str(clone_dir),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")

        return clone_dir

    def detect_entrypoint(self, repo_path: Path) -> Optional[str]:
        """Detect the Python entrypoint in the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            Entrypoint string or None if not found
        """
        # Check for __main__.py at root
        main_py = repo_path / "__main__.py"
        if main_py.exists():
            return "main"

        # Check for main.py at root
        main_file = repo_path / "main.py"
        if main_file.exists():
            return "main"

        # Check pyproject.toml for console scripts
        pyproject_toml = repo_path / "pyproject.toml"
        if pyproject_toml.exists():
            try:
                # Try tomllib first (Python 3.11+)
                try:
                    import tomllib

                    with open(pyproject_toml, "rb") as f:
                        data = tomllib.load(f)
                except ImportError:
                    # Fallback to toml for older Python versions
                    import toml

                    with open(pyproject_toml, "r") as f:
                        data = toml.load(f)

                scripts = data.get("project", {}).get("scripts", {})
                if scripts:
                    # Return the first console script
                    first_script = next(iter(scripts.keys()))
                    return first_script
            except Exception:
                pass

        # Check for setup.py
        setup_py = repo_path / "setup.py"
        if setup_py.exists():
            try:
                # Simple parsing for entry_points
                with open(setup_py, "r") as f:
                    content = f.read()
                    if "entry_points" in content:
                        # This is a simplified approach - in production you'd want proper parsing
                        return "main"
            except Exception:
                pass

        # Look for package with __main__.py
        for item in repo_path.iterdir():
            if item.is_dir() and (item / "__main__.py").exists():
                return f"{item.name}.main"

        # Check for app.py or app/main.py
        app_py = repo_path / "app.py"
        if app_py.exists():
            return "app"

        app_dir = repo_path / "app"
        if app_dir.exists() and app_dir.is_dir():
            app_main = app_dir / "__main__.py"
            if app_main.exists():
                return "app.main"
            app_py = app_dir / "app.py"
            if app_py.exists():
                return "app.app"

        # Check for src/ directory with package
        src_dir = repo_path / "src"
        if src_dir.exists() and src_dir.is_dir():
            for item in src_dir.iterdir():
                if item.is_dir() and (item / "__main__.py").exists():
                    return f"{item.name}.main"

        # Check for any Python file with main function
        for py_file in repo_path.glob("*.py"):
            if py_file.name.startswith("main") or py_file.name.startswith("app"):
                try:
                    with open(py_file, "r") as f:
                        content = f.read()
                        if (
                            "def main(" in content
                            or 'if __name__ == "__main__"' in content
                        ):
                            return py_file.stem
                except Exception:
                    continue

        return None

    def cleanup_cache(self, max_age_days: int = 7) -> None:
        """Clean up old cached repositories.

        Args:
            max_age_days: Maximum age in days for cached repositories
        """
        import time

        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60

        for item in self.cache_dir.iterdir():
            if item.is_dir():
                try:
                    mtime = item.stat().st_mtime
                    if current_time - mtime > max_age_seconds:
                        import shutil

                        shutil.rmtree(item)
                except Exception:
                    # Skip items that can't be removed
                    pass
