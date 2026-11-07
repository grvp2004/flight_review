"""Local upload behavior, including optional full-size streaming verification."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from tornado.httpclient import HTTPRequest
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tornado_handlers import upload
from tornado_handlers import send_email
from config import get_max_upload_size


class LocalUploadTests(AsyncHTTPTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = MagicMock()
        self.loader = MagicMock(return_value=SimpleNamespace(msg_info_dict={}))
        replacements = {
            'is_local_only': lambda: True,
            'get_log_filename': lambda log_id: str(Path(self.directory.name) / (log_id + '.ulg')),
            'get_db_connection': lambda: self.db,
            'load_ulog_file': self.loader,
            'update_vehicle_db_entry': lambda *args: SimpleNamespace(name=''),
        }
        for name, value in replacements.items():
            patcher = patch.object(upload, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        super().setUp()

    def get_app(self):
        return Application([(r'/upload', upload.UploadHandler)])

    def get_httpserver_options(self):
        return {'max_buffer_size': 8 * 1024 * 1024,
                'max_body_size': get_max_upload_size() + 1024 * 1024}

    async def stream_file(self, size, fields=None, valid=True):
        boundary = 'local-upload-test-boundary'
        prefix = b''
        for key, value in (fields or {}).items():
            prefix += (f'--{boundary}\r\nContent-Disposition: form-data; '
                       f'name="{key}"\r\n\r\n{value}\r\n').encode()
        prefix += (f'--{boundary}\r\nContent-Disposition: form-data; '
                   'name="filearg"; filename="test.ulg"\r\n'
                   'Content-Type: application/octet-stream\r\n\r\n').encode()
        suffix = f'\r\n--{boundary}--\r\n'.encode()
        magic = upload.ULog.HEADER_BYTES if valid else b'INVALID'

        async def produce(write):
            await write(prefix)
            await write(magic)
            remaining = size - len(magic)
            chunk = bytes(min(1024 * 1024, remaining))
            while remaining:
                count = min(len(chunk), remaining)
                await write(chunk[:count])
                remaining -= count
            await write(suffix)

        request = HTTPRequest(self.get_url('/upload'), method='POST',
                              headers={'Content-Type': f'multipart/form-data; boundary={boundary}',
                                       'Content-Length': str(len(prefix) + size + len(suffix))},
                              body_producer=produce, request_timeout=180)
        return await self.http_client.fetch(request, raise_error=False)

    def test_form_has_no_email_or_sharing(self):
        response = self.fetch('/upload')
        self.assertEqual(response.code, 200)
        html = response.body.decode()
        self.assertNotIn('name="email"', html)
        self.assertNotIn('name="public"', html)
        self.assertIn('data-max-size="1073741824"', html)

    @gen_test
    async def test_no_email_required_and_sharing_fields_ignored(self):
        with patch.object(upload, 'send_notification_email') as email, \
                patch.object(upload, 'send_flightreport_email') as report, \
                patch.object(upload, 'get_airframe_name') as remote_metadata:
            response = await self.stream_file(2048, {
                'type': 'flightreport', 'public': 'true', 'allowForAnalysis': 'true',
                'email': 'ignored@example.com', 'source': 'CI',
            })
        self.assertEqual(response.code, 200, response.body)
        self.assertTrue(json.loads(response.body)['url'].startswith('/plot_app?log='))
        values = self.db.cursor.return_value.execute.call_args.args[1]
        self.assertEqual(values[5], 0)   # AllowForAnalysis
        self.assertEqual(values[7], 'webui')
        self.assertEqual(values[8], '')  # Email
        self.assertEqual(values[12], 'personal')
        self.assertEqual(values[15], 0)  # Public
        email.assert_not_called()
        report.assert_not_called()
        remote_metadata.assert_not_called()
        self.loader.assert_called_once()

    @gen_test
    async def test_size_boundary_and_over_limit(self):
        with patch.object(upload, 'get_max_upload_size', return_value=2048):
            accepted = await self.stream_file(2048)
            rejected = await self.stream_file(2049)
        self.assertEqual(accepted.code, 200, accepted.body)
        self.assertEqual(rejected.code, 413, rejected.body)
        self.assertIn('1 GB', json.loads(rejected.body)['error'])
        self.assertEqual(self.loader.call_count, 1)

    @gen_test
    async def test_invalid_file_returns_useful_error(self):
        response = await self.stream_file(1024, valid=False)
        self.assertEqual(response.code, 400)
        self.assertEqual(json.loads(response.body)['error'], 'Invalid File')
        self.loader.assert_not_called()

    def test_email_transport_disabled(self):
        with patch.object(send_email, 'is_local_only', return_value=True), \
                patch.object(send_email, 'SMTP') as smtp:
            self.assertTrue(send_email._send_email(['ignored@example.com'], 'test', 'test'))
        smtp.assert_not_called()

    @unittest.skipUnless(os.environ.get('LARGE_UPLOAD_TEST') == '1', 'optional 1 GB disk test')
    @gen_test(timeout=180)
    async def test_full_one_gb_stream(self):
        response = await self.stream_file(1024 ** 3)
        self.assertEqual(response.code, 200, response.body)
        path = Path(self.loader.call_args.args[0])
        self.assertEqual(path.stat().st_size, 1024 ** 3)


if __name__ == '__main__':
    unittest.main()
