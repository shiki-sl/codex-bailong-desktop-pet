import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import linux_support as linux


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux desktop integration')
class LinuxIntegrationTests(unittest.TestCase):
    def test_startup_is_opt_in_and_uses_the_actual_venv(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_CONFIG_HOME': folder}), patch.object(linux.sys, 'executable', '/tmp/example venv/bin/python'):
            path = linux.startup_path()
            self.assertFalse(path.exists())
            linux.register_startup(True)
            text = path.read_text()
            self.assertIn('"/tmp/example venv/bin/python"', text)
            self.assertNotIn('pythonw.exe', text)
            linux.register_startup(False)
            self.assertFalse(path.exists())

    def test_chat_key_is_sent_over_stdin_to_secret_service(self):
        with patch.object(linux.shutil, 'which', return_value='/usr/bin/secret-tool'), patch.object(linux.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            linux.SecretStore('/tmp/chat-keys.json').put('example', 'test-only-key')
            args, options = run.call_args
            self.assertNotIn('test-only-key', repr(args))
            self.assertEqual(options['input'], 'test-only-key')
            self.assertIn('store', args[0])

    def test_missing_keyring_never_falls_back_to_plaintext(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(linux.shutil, 'which', return_value=None):
            path = Path(folder) / 'keys.json'
            with self.assertRaises(OSError):
                linux.SecretStore(path).put('example', 'test-only-key')
            self.assertFalse(path.exists())

    def test_unix_transport_reads_and_writes_the_framed_stream(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            path = home / 'ipc/ipc.sock'
            path.parent.mkdir()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            server.listen(1)
            received = []
            def serve():
                with server.accept()[0] as client:
                    received.append(client.recv(2))
                    client.sendall(b'ok')
            worker = threading.Thread(target=serve)
            worker.start()
            class Reader:
                stop_event = threading.Event()
                connected = False
                def _listen(self, stream, available):
                    stream.write(b'hi')
                    received.append(stream.read(2))
                    self.stop_event.set()
                def set_health(self, *args):
                    raise AssertionError(args)
            with patch('codex_connection.data_home', return_value=home):
                linux.ipc_listen(Reader())
            worker.join(2)
            server.close()
            self.assertEqual(received, [b'hi', b'ok'])

    def test_ipc_never_connects_to_another_users_socket(self):
        stop = threading.Event()
        reader = SimpleNamespace(stop_event=stop, connected=False)
        reader.set_health = lambda *args: stop.set()
        foreign = SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=os.getuid()+1)
        with tempfile.TemporaryDirectory() as folder, patch('codex_connection.data_home', return_value=Path(folder)), patch.object(Path, 'lstat', return_value=foreign), patch('socket.socket') as connect:
            linux.ipc_listen(reader)
        connect.assert_not_called()

    def test_stale_primary_socket_does_not_hide_a_live_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            primary = home / 'ipc/ipc.sock'
            fallback = home / 'fallback'
            primary.parent.mkdir()
            fallback.mkdir()
            received = []
            stop = threading.Event()
            reader = SimpleNamespace(stop_event=stop, connected=False)
            reader.set_health = lambda *args: stop.set()
            def listen(stream, available):
                stream.write(b'hi')
                received.append(stream.read(2))
                stop.set()
            reader._listen = listen
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                stale.bind(str(primary))  # A socket path exists, but nobody listens.
                server.bind(str(fallback / f'ipc-{os.getuid()}.sock'))
                server.listen(1)
                server.settimeout(1)
                def serve():
                    try:
                        with server.accept()[0] as client:
                            received.append(client.recv(2))
                            client.sendall(b'ok')
                    except socket.timeout:
                        pass
                worker = threading.Thread(target=serve)
                worker.start()
                with patch('codex_connection.data_home', return_value=home), patch.object(linux, 'Path', return_value=fallback):
                    linux.ipc_listen(reader)
                worker.join(2)
            self.assertEqual(received, [b'hi', b'ok'])

    def test_linux_never_starts_a_windows_update_or_install_job(self):
        from update_controller import UpdateController
        with tempfile.TemporaryDirectory() as folder:
            controller = UpdateController('0.8.8', Path(folder), allow_auto=False)
            with patch('update_controller.UpdateJob') as job:
                self.assertFalse(controller.check())
                self.assertFalse(controller.download_install())
                job.assert_not_called()
            self.assertIn('Windows', controller.state['message'])
            controller.shutdown()

    def test_windows_update_check_keeps_the_existing_job_route(self):
        from update_controller import UpdateController
        with tempfile.TemporaryDirectory() as folder:
            controller = UpdateController('0.8.8', Path(folder), allow_auto=False)
            with patch('update_controller.sys.platform', 'win32'), patch('update_controller.UpdateJob') as job, patch.object(controller, '_bind') as bind:
                self.assertTrue(controller.check())
                bind.assert_called_once_with(job.return_value)
            controller.shutdown()


if __name__ == '__main__':
    unittest.main()
