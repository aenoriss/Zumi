"""Zumi pipeline. Stages are plain functions; the CLI wires them."""

import os

FORMAT_VERSION = "1.0.0"
GENERATOR = "zumi-pipeline 0.1.0"
WORKERS = min(8, os.cpu_count() or 1)  # threads for numpy and Pillow work that releases the GIL
