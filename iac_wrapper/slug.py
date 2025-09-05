"""Repository slug parsing and validation."""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass
class RepoSlug:
    """Repository slug information."""

    scheme: str
    owner: str
    repo: str
    ref: Optional[str] = None

    def __post_init__(self):
        """Validate the slug after initialization."""
        if not self.scheme:
            raise ValueError("Scheme is required")
        if not self.owner:
            raise ValueError("Owner is required")
        if not self.repo:
            raise ValueError("Repository name is required")

    @property
    def full_name(self) -> str:
        """Get the full repository name."""
        return f"{self.owner}/{self.repo}"

    @property
    def service_name(self) -> str:
        """Get the service name for Docker."""
        return f"{self.owner}-{self.repo}".replace("/", "-").lower()

    @property
    def archive_url(self) -> str:
        """Get the archive URL for the repository."""
        if self.scheme == "gh":
            base_url = f"https://github.com/{self.full_name}"
            if self.ref:
                return f"{base_url}/archive/{self.ref}.tar.gz"
            return f"{base_url}/archive/refs/heads/main.tar.gz"
        elif self.scheme == "gl":
            base_url = f"https://gitlab.com/{self.full_name}"
            if self.ref:
                return f"{base_url}/-/archive/{self.ref}/{self.repo}-{self.ref}.tar.gz"
            return f"{base_url}/-/archive/main/{self.repo}-main.tar.gz"
        else:
            raise ValueError(f"Unsupported scheme: {self.scheme}")

    @property
    def clone_url(self) -> str:
        """Get the clone URL for the repository."""
        if self.scheme == "gh":
            return f"https://github.com/{self.full_name}.git"
        elif self.scheme == "gl":
            return f"https://gitlab.com/{self.full_name}.git"
        else:
            raise ValueError(f"Unsupported scheme: {self.scheme}")

    def __str__(self) -> str:
        """String representation of the slug."""
        result = f"{self.scheme}:{self.full_name}"
        if self.ref:
            result += f"#{self.ref}"
        return result


def parse_slug(slug: str) -> RepoSlug:
    """Parse a repository slug into its components.

    Args:
        slug: Repository slug in format 'scheme:owner/repo[#ref]'

    Returns:
        RepoSlug object with parsed components

    Raises:
        ValueError: If the slug format is invalid
    """
    # Pattern: scheme:owner/repo[#ref]
    pattern = r"^([a-zA-Z]+):([^/]+/[^#]+)(?:#(.+))?$"
    match = re.match(pattern, slug)

    if not match:
        raise ValueError(
            f"Invalid slug format: {slug}. Expected format: scheme:owner/repo[#ref]"
        )

    scheme, full_name, ref = match.groups()

    # Validate owner/repo format
    if "/" not in full_name:
        raise ValueError(
            f"Invalid repository format: {full_name}. Expected: owner/repo"
        )

    owner, repo = full_name.split("/", 1)

    # Validate components
    if not owner or not repo:
        raise ValueError(f"Invalid owner or repository name: {full_name}")

    return RepoSlug(scheme=scheme.lower(), owner=owner, repo=repo, ref=ref)


def validate_slug(slug: str) -> bool:
    """Validate if a slug has the correct format.

    Args:
        slug: Repository slug to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        if slug is None:
            return False
        parse_slug(slug)
        return True
    except (ValueError, TypeError):
        return False


def normalize_slug(slug: str) -> str:
    """Normalize a slug to standard format.

    Args:
        slug: Repository slug to normalize

    Returns:
        Normalized slug string
    """
    repo_slug = parse_slug(slug)
    return str(repo_slug)
