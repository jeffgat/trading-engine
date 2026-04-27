#!/usr/bin/env python3
"""Run the first-pass Gold-X v14.4 core replication."""

from __future__ import annotations

import sys

from reverse_engineer_goldx import main


if __name__ == "__main__":
    if "--run-sim" not in sys.argv:
        sys.argv.append("--run-sim")
    main()
