"""JR must reject mutations before reaching Resolve on an inactive machine."""
import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import types
import unittest
from unittest.mock import patch
import controller
from player import LicenseError

class LicenseHttpTests(unittest.TestCase):
    def test_inactive_jr_cannot_mutate_resolve(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),controller.handler(types.SimpleNamespace()))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with patch.object(controller,'require_active',side_effect=LicenseError('Activation required')),patch.object(controller,'lua_call') as lua:
                for func in ('ExportAudio','AddSubtitles','GeneratePreview','StartPresetEdit','CapturePresetSettings'):
                    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    connection.request('POST','/',json.dumps({'func':func}))
                    response=json.loads(connection.getresponse().read())
                    connection.close()
                    self.assertTrue(response['error'])
                    self.assertEqual(response['detail'],'Activation required')
                lua.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
