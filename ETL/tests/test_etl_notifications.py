import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ETL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('notifications', ETL/'src/runtime/etl_notifications.py')
notifications = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notifications)


class NotificationsTest(unittest.TestCase):
    def test_failure_persists_without_opening_window(self):
        root = ETL/'output/temp/tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory, patch.object(notifications.subprocess, 'Popen') as popen:
            alert = notifications.notify_failure('device', 'exit 1', 'D:/step.log', popup=False, alert_dir=directory)
            payload = json.loads(alert.read_text())
            self.assertEqual(payload['step'], 'device')
            self.assertFalse(payload['acknowledged'])
            popen.assert_not_called()

    def test_popup_receives_file_not_error_as_executable_code(self):
        root = ETL/'output/temp/tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory, patch.object(notifications.subprocess, 'Popen') as popen, patch.dict(notifications.os.environ, {'VG_ETL_NOTIFY_FAILURES':'1'}):
            alert = notifications.notify_failure('device', 'quotes " and ; are text', alert_dir=directory)
            args = popen.call_args.args[0]
            self.assertEqual(args[-2:], ['-AlertFile', str(alert)])
            self.assertNotIn('quotes " and ; are text', args)


if __name__ == '__main__':
    unittest.main()
