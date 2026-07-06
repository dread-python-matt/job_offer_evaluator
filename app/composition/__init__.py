"""Composition root, split into small builders.

`main.py` is a thin entry point: it calls `build_app()` from here to assemble the FastAPI
application, wiring every port to a concrete adapter. The wiring is grouped by concern —
`foundation` (engine + repositories + shared primitives), `offers`, `auth`, `usage`, and `ai` —
and `app_factory.build_app()` orchestrates them. This is the one place that depends on every
layer's concrete types; the domain and application layers stay framework-free.
"""

from app.composition.app_factory import build_app

__all__ = ["build_app"]
