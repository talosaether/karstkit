"""Tests for slug parsing functionality."""

import pytest
from iac_wrapper.slug import parse_slug, validate_slug, normalize_slug, RepoSlug


class TestRepoSlug:
    """Test RepoSlug class."""

    def test_valid_slug_creation(self):
        """Test creating a valid RepoSlug."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")
        assert slug.scheme == "gh"
        assert slug.owner == "testuser"
        assert slug.repo == "testrepo"
        assert slug.ref is None

    def test_slug_with_ref(self):
        """Test creating a RepoSlug with ref."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo", ref="v1.0.0")
        assert slug.ref == "v1.0.0"

    def test_full_name_property(self):
        """Test the full_name property."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")
        assert slug.full_name == "testuser/testrepo"

    def test_service_name_property(self):
        """Test the service_name property."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")
        assert slug.service_name == "testuser-testrepo"

    def test_archive_url_github(self):
        """Test archive URL generation for GitHub."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")
        expected = "https://github.com/testuser/testrepo/archive/refs/heads/main.tar.gz"
        assert slug.archive_url == expected

    def test_archive_url_github_with_ref(self):
        """Test archive URL generation for GitHub with ref."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo", ref="v1.0.0")
        expected = "https://github.com/testuser/testrepo/archive/v1.0.0.tar.gz"
        assert slug.archive_url == expected

    def test_archive_url_gitlab(self):
        """Test archive URL generation for GitLab."""
        slug = RepoSlug(scheme="gl", owner="testuser", repo="testrepo")
        expected = (
            "https://gitlab.com/testuser/testrepo/-/archive/main/testrepo-main.tar.gz"
        )
        assert slug.archive_url == expected

    def test_clone_url_github(self):
        """Test clone URL generation for GitHub."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")
        expected = "https://github.com/testuser/testrepo.git"
        assert slug.clone_url == expected

    def test_clone_url_gitlab(self):
        """Test clone URL generation for GitLab."""
        slug = RepoSlug(scheme="gl", owner="testuser", repo="testrepo")
        expected = "https://gitlab.com/testuser/testrepo.git"
        assert slug.clone_url == expected

    def test_string_representation(self):
        """Test string representation."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")
        assert str(slug) == "gh:testuser/testrepo"

    def test_string_representation_with_ref(self):
        """Test string representation with ref."""
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo", ref="v1.0.0")
        assert str(slug) == "gh:testuser/testrepo#v1.0.0"

    def test_validation_missing_scheme(self):
        """Test validation with missing scheme."""
        with pytest.raises(ValueError, match="Scheme is required"):
            RepoSlug(scheme="", owner="testuser", repo="testrepo")

    def test_validation_missing_owner(self):
        """Test validation with missing owner."""
        with pytest.raises(ValueError, match="Owner is required"):
            RepoSlug(scheme="gh", owner="", repo="testrepo")

    def test_validation_missing_repo(self):
        """Test validation with missing repo."""
        with pytest.raises(ValueError, match="Repository name is required"):
            RepoSlug(scheme="gh", owner="testuser", repo="")


class TestParseSlug:
    """Test parse_slug function."""

    def test_parse_valid_github_slug(self):
        """Test parsing a valid GitHub slug."""
        slug = parse_slug("gh:testuser/testrepo")
        assert slug.scheme == "gh"
        assert slug.owner == "testuser"
        assert slug.repo == "testrepo"
        assert slug.ref is None

    def test_parse_valid_github_slug_with_ref(self):
        """Test parsing a valid GitHub slug with ref."""
        slug = parse_slug("gh:testuser/testrepo#v1.0.0")
        assert slug.scheme == "gh"
        assert slug.owner == "testuser"
        assert slug.repo == "testrepo"
        assert slug.ref == "v1.0.0"

    def test_parse_valid_gitlab_slug(self):
        """Test parsing a valid GitLab slug."""
        slug = parse_slug("gl:testuser/testrepo")
        assert slug.scheme == "gl"
        assert slug.owner == "testuser"
        assert slug.repo == "testrepo"

    def test_parse_slug_with_branch_ref(self):
        """Test parsing a slug with branch ref."""
        slug = parse_slug("gh:testuser/testrepo#develop")
        assert slug.ref == "develop"

    def test_parse_slug_with_commit_ref(self):
        """Test parsing a slug with commit ref."""
        slug = parse_slug("gh:testuser/testrepo#abc123")
        assert slug.ref == "abc123"

    def test_parse_invalid_format(self):
        """Test parsing invalid slug format."""
        with pytest.raises(ValueError, match="Invalid slug format"):
            parse_slug("invalid-slug")

    def test_parse_missing_scheme(self):
        """Test parsing slug without scheme."""
        with pytest.raises(ValueError, match="Invalid slug format"):
            parse_slug("testuser/testrepo")

    def test_parse_missing_owner(self):
        """Test parsing slug without owner."""
        with pytest.raises(ValueError, match="Invalid slug format"):
            parse_slug("gh:/testrepo")

    def test_parse_missing_repo(self):
        """Test parsing slug without repo."""
        with pytest.raises(ValueError, match="Invalid slug format"):
            parse_slug("gh:testuser/")

    def test_parse_empty_components(self):
        """Test parsing slug with empty components."""
        with pytest.raises(ValueError, match="Invalid slug format"):
            parse_slug("gh://")


class TestValidateSlug:
    """Test validate_slug function."""

    def test_validate_valid_slug(self):
        """Test validating a valid slug."""
        assert validate_slug("gh:testuser/testrepo") is True

    def test_validate_valid_slug_with_ref(self):
        """Test validating a valid slug with ref."""
        assert validate_slug("gh:testuser/testrepo#v1.0.0") is True

    def test_validate_invalid_slug(self):
        """Test validating an invalid slug."""
        assert validate_slug("invalid-slug") is False

    def test_validate_empty_string(self):
        """Test validating empty string."""
        assert validate_slug("") is False

    def test_validate_none(self):
        """Test validating None."""
        assert validate_slug(None) is False


class TestNormalizeSlug:
    """Test normalize_slug function."""

    def test_normalize_valid_slug(self):
        """Test normalizing a valid slug."""
        result = normalize_slug("gh:testuser/testrepo")
        assert result == "gh:testuser/testrepo"

    def test_normalize_slug_with_ref(self):
        """Test normalizing a slug with ref."""
        result = normalize_slug("gh:testuser/testrepo#v1.0.0")
        assert result == "gh:testuser/testrepo#v1.0.0"

    def test_normalize_invalid_slug(self):
        """Test normalizing an invalid slug."""
        with pytest.raises(ValueError):
            normalize_slug("invalid-slug")
