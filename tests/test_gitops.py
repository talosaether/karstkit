"""Tests for git operations functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from iac_wrapper.gitops import GitOps
from iac_wrapper.slug import RepoSlug


class TestGitOps:
    """Test GitOps class."""

    def test_init_with_default_cache_dir(self, temp_dir):
        """Test GitOps initialization with default cache directory."""
        git_ops = GitOps()
        assert git_ops.cache_dir.exists()
        assert git_ops.cache_dir.is_dir()

    def test_init_with_custom_cache_dir(self, temp_dir):
        """Test GitOps initialization with custom cache directory."""
        custom_cache = temp_dir / "custom_cache"
        git_ops = GitOps(cache_dir=custom_cache)
        assert git_ops.cache_dir == custom_cache
        assert custom_cache.exists()

    @patch("requests.get")
    def test_fetch_repo_archive_success(self, mock_get, temp_dir):
        """Test successful repository fetch via archive."""
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = [b"fake tar content"]
        mock_get.return_value = mock_response

        # Mock tarfile extraction
        with patch("tarfile.open") as mock_tar:
            mock_tar.return_value.__enter__.return_value.getmembers.return_value = [
                Mock(name="testrepo-1.0.0/file1.py"),
                Mock(name="testrepo-1.0.0/file2.py"),
            ]

            git_ops = GitOps(cache_dir=temp_dir)
            slug = RepoSlug(
                scheme="gh", owner="testuser", repo="testrepo", ref="v1.0.0"
            )

            result = git_ops.fetch_repo(slug)

            assert result.exists()
            assert result.is_dir()
            assert "testrepo-v1.0.0" in str(result)

    @patch("subprocess.run")
    def test_fetch_repo_clone_success(self, mock_run, temp_dir):
        """Test successful repository fetch via clone."""
        # Mock successful git clone
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        git_ops = GitOps(cache_dir=temp_dir)
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")

        result = git_ops.fetch_repo(slug)

        assert result.exists()
        assert result.is_dir()
        assert "testuser-testrepo" in str(result)

        # Verify git clone was called with correct parameters
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "git"
        assert call_args[1] == "clone"
        assert call_args[2] == "--depth"
        assert call_args[3] == "1"
        assert call_args[4] == "--single-branch"
        assert call_args[5] == "--branch"
        assert call_args[6] == "main"
        assert call_args[7] == "https://github.com/testuser/testrepo.git"

    @patch("requests.get")
    @patch("subprocess.run")
    def test_fetch_repo_fallback_to_clone(self, mock_run, mock_get, temp_dir):
        """Test fallback to clone when archive fails."""
        # Mock failed HTTP request
        mock_get.side_effect = Exception("HTTP Error")

        # Mock successful git clone
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        git_ops = GitOps(cache_dir=temp_dir)
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")

        result = git_ops.fetch_repo(slug)

        assert result.exists()
        assert result.is_dir()
        mock_run.assert_called_once()

    @patch("requests.get")
    @patch("subprocess.run")
    def test_fetch_repo_both_fail(self, mock_run, mock_get, temp_dir):
        """Test when both archive and clone fail."""
        # Mock failed HTTP request
        mock_get.side_effect = Exception("HTTP Error")

        # Mock failed git clone
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Git clone failed"

        git_ops = GitOps(cache_dir=temp_dir)
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")

        with pytest.raises(RuntimeError, match="Failed to fetch repository"):
            git_ops.fetch_repo(slug)

    def test_detect_entrypoint_main_py(self, sample_repo):
        """Test entrypoint detection with main.py."""
        git_ops = GitOps()
        entrypoint = git_ops.detect_entrypoint(sample_repo)
        assert entrypoint == "main"

    def test_detect_entrypoint_main_module(self, sample_repo_with_package):
        """Test entrypoint detection with package __main__.py."""
        git_ops = GitOps()
        entrypoint = git_ops.detect_entrypoint(sample_repo_with_package)
        assert entrypoint == "sample_package.main"

    def test_detect_entrypoint_pyproject_scripts(self, temp_dir):
        """Test entrypoint detection with pyproject.toml scripts."""
        repo_dir = temp_dir / "test-repo"
        repo_dir.mkdir()

        # Create pyproject.toml with scripts
        pyproject_content = """
[project]
name = "test-app"
version = "0.1.0"

[project.scripts]
my-app = "main:main"
another-app = "other:main"
"""
        pyproject_file = repo_dir / "pyproject.toml"
        pyproject_file.write_text(pyproject_content)

        git_ops = GitOps()
        entrypoint = git_ops.detect_entrypoint(repo_dir)
        assert entrypoint == "my-app"

    def test_detect_entrypoint_setup_py(self, temp_dir):
        """Test entrypoint detection with setup.py."""
        repo_dir = temp_dir / "test-repo"
        repo_dir.mkdir()

        # Create setup.py with entry_points
        setup_content = """
from setuptools import setup

setup(
    name="test-app",
    version="0.1.0",
    entry_points={
        'console_scripts': [
            'my-app=main:main',
        ],
    },
)
"""
        setup_file = repo_dir / "setup.py"
        setup_file.write_text(setup_content)

        git_ops = GitOps()
        entrypoint = git_ops.detect_entrypoint(repo_dir)
        assert entrypoint == "main"

    def test_detect_entrypoint_none_found(self, temp_dir):
        """Test entrypoint detection when none found."""
        repo_dir = temp_dir / "test-repo"
        repo_dir.mkdir()

        # Create a file that's not an entrypoint
        readme_file = repo_dir / "README.md"
        readme_file.write_text("# Test Repo")

        git_ops = GitOps()
        entrypoint = git_ops.detect_entrypoint(repo_dir)
        assert entrypoint is None

    def test_cleanup_cache(self, temp_dir):
        """Test cache cleanup functionality."""
        git_ops = GitOps(cache_dir=temp_dir)

        # Create some test directories
        old_dir = temp_dir / "old-repo"
        old_dir.mkdir()

        new_dir = temp_dir / "new-repo"
        new_dir.mkdir()

        # Mock time to make old_dir appear old
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000000000  # Some future time

            # Set old modification time for old_dir
            old_time = 1000000000 - (10 * 24 * 60 * 60)  # 10 days ago
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_mtime = old_time

                git_ops.cleanup_cache(max_age_days=7)

                # old_dir should be removed, new_dir should remain
                assert not old_dir.exists()
                assert new_dir.exists()

    def test_fetch_repo_cached(self, temp_dir):
        """Test that fetch_repo returns cached directory if it exists."""
        git_ops = GitOps(cache_dir=temp_dir)
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")

        # Create cached directory
        cached_dir = temp_dir / "testuser-testrepo"
        cached_dir.mkdir()

        # Create a file in the cached directory
        test_file = cached_dir / "test.txt"
        test_file.write_text("cached content")

        # Mock requests to ensure we don't actually fetch
        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("Should not be called")

            result = git_ops.fetch_repo(slug)

            # Should return the cached directory
            assert result == cached_dir
            assert result.exists()
            assert (result / "test.txt").read_text() == "cached content"
