import sys
import unittest


sys.path.insert(0, "..")

from androidtv_wifi import constants
from androidtv_wifi.androidtv.base_androidtv import BaseAndroidTV
from androidtv_wifi.firetv.base_firetv import BaseFireTV


class TestBaseTV(unittest.TestCase):
    def test_base_android_tv(self):
        """Test that ``BaseAndroidTV.__init__`` runs without error."""
        BaseAndroidTV("host")

    def test_base_fire_tv(self):
        """Test that ``BaseFireTV.__init__`` runs without error."""
        BaseFireTV("host")
