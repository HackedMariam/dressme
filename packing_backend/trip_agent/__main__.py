"""Allow `python -m packing_backend.trip_agent`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
