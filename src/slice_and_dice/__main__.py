"""Allow running the shell with ``python -m slice_and_dice``."""

from slice_and_dice.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
