from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch

from ad_host.v26_gui import App


class ConnectGuardTests(TestCase):
    def test_second_connect_does_not_replace_live_session(self):
        live=Mock();live.wait.return_value=False
        app=SimpleNamespace(session=live,timeout=Mock())
        app.timeout.get.side_effect=AssertionError('Connection settings must not be read again')
        with patch('ad_host.v26_gui.V26Session') as constructor:
            App.connect(app)
        constructor.assert_not_called()
        self.assertIs(app.session,live)
