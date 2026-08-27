"""Vercel serverless entrypoint for the Code Nexus Flask application.

Vercel's Python runtime serves the module-level WSGI callable named ``app``.
Every route (static frontend + JSON API) is handled by the Flask app in
``backend/app.py``; see ``vercel.json`` for the catch-all rewrite.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# The project filesystem is read-only on Vercel; only /tmp is writable.
os.environ.setdefault("CODENEXUS_DB", "/tmp/code_nexus.db")

from backend.app import app  # noqa: E402  (path set up above)

# Expose the WSGI app for the Vercel Python runtime.
application = app
