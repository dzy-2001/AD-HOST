from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


class ResourceTests(unittest.TestCase):
    def test_assets_resolve_independently_of_current_directory(self):
        from src.resources import resource_path
        expected=Path(__file__).resolve().parents[1]/'assets/logo.ico'
        before=Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertEqual(resource_path('assets/logo.ico'),expected)
                self.assertEqual(resource_path('assets/logo.ico').read_bytes()[:4],b'\x00\x00\x01\x00')
            finally:os.chdir(before)

    def test_frozen_resources_use_bundle_root(self):
        from src.resources import resource_path
        with tempfile.TemporaryDirectory() as directory,patch.object(sys,'_MEIPASS',directory,create=True):
            root=Path(directory);(root/'assets').mkdir();(root/'assets/splash.png').write_bytes(b'packed splash')
            self.assertEqual(resource_path('assets/splash.png').read_bytes(),b'packed splash')
