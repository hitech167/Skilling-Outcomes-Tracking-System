"""
Vercel Python entry point.

Vercel's Python runtime looks for an ASGI/WSGI app object in the file it
builds. The actual application lives in main.py at the project root, one
level up from this api/ folder — this file just re-exports it.
"""

from main import app  # noqa: F401
