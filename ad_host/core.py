"""Compatibility import; implementation lives in src.models.core."""
import sys
from src.models import core as _implementation
sys.modules[__name__] = _implementation
