"""Earth Engine initialization state shared across the app.

Importing this module attempts a single `ee.Initialize` (cached credentials,
same behavior the app has always had at startup). `earth_engine_ready` is the
one flag /analyze, /predict and the health endpoints agree on — when it is
False those endpoints report live satellite data as unavailable instead of
inventing values.
"""
import os
from typing import Optional

from app import config as app_config

earth_engine_ready = False
earth_engine_error: str | None = None
_current_project: str | None = None

try:
    import ee  # noqa: F401  (re-exported implicitly for callers that re-import)
except ImportError:
    ee = None


def init_earth_engine(project_id: Optional[str] = None) -> bool:
    """Initialize Google Earth Engine safely and update shared runtime state."""
    global earth_engine_ready, earth_engine_error, _current_project
    proj = project_id or os.getenv("GEE_PROJECT", app_config.GEE_PROJECT)

    if earth_engine_ready and _current_project == proj:
        return True

    try:
        import ee as _ee
        _ee.Initialize(project=proj)
        earth_engine_ready = True
        earth_engine_error = None
        _current_project = proj
        print(f"Earth Engine initialized with project: {proj}")
        return True
    except Exception as e:
        earth_engine_ready = False
        earth_engine_error = str(e)
        print(f"Earth Engine not available: {e}")
        return False


# Attempt startup initialization with configured project
init_earth_engine()
