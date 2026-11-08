"""Compatibility module for ``python -m cvagent.postgres_setup``."""

from .cli.postgres_setup import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
