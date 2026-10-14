"""Compatibility import; implementation lives in src.models.v26_transport."""
import sys
from src.models import v26_transport as _implementation
sys.modules[__name__] = _implementation
