"""Built-in pattern registration helpers."""

from __future__ import annotations

_BUILTINS_LOADED = False


def load_builtin_patterns() -> None:
    """Load built-in patterns and their side-effect registrations once.

    CLI and tests can call this without knowing individual pattern module names.
    Pattern-specific imports stay in the pattern package, not generic CLI code.
    """
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return

    from . import aws_lza as _aws_lza  # noqa: F401
    from . import kubernetes as _kubernetes  # noqa: F401
    from . import terraform_vpc as _terraform_vpc  # noqa: F401

    _BUILTINS_LOADED = True
