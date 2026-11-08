"""Compatibility module for ``python -m cvagent.demo``."""

from .cli.demo import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
