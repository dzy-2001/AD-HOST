"""Compatibility import; implementation lives in src.models.recording."""
import sys
from src.models import recording as _implementation
sys.modules[__name__] = _implementation
