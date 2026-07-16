"""Installed package identity."""

from importlib.metadata import PackageNotFoundError, version


def installed_version() -> str:
    """Return the installed distribution version or the source-tree fallback."""
    try:
        return version("iac-llm-wrapper")
    except PackageNotFoundError:
        return "0+unknown"
