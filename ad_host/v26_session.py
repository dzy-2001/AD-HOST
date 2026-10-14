"""Compatibility import; implementation lives in src.models.v26_session."""
import sys
from src.models import v26_session as _implementation
sys.modules[__name__] = _implementation
