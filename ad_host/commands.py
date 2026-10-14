"""Compatibility import; implementation lives in src.models.commands."""
import sys
from src.models import commands as _implementation
sys.modules[__name__] = _implementation
