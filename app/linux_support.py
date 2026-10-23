"""Linux integration for the upstream Bailong desktop UI.

Codex data remains read-only. Runtime data belongs to this app's XDG directory.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys


def data_root():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))


def configure_environment():
    # Compatibility for upstream modules; never change the parent environment.
    os.environ.setdefault('LOCALAPPDATA', str(data_root()))
    os.environ.setdefault('APPDATA', str(Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))))
    # Wayland does not allow QWidget.move(), required for linked card placement.
    if os.environ.get('WAYLAND_DISPLAY') and os.environ.get('DISPLAY'):
        os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')
    os.umask(0o077)


def app_command():
    # Keep the venv executable, rather than resolving its interpreter symlink.
    return [sys.executable, str(Path(__file__).with_name('enhanced.py'))]


def startup_path(watcher=False):
    root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return root / 'autostart' / ('bailong-codex-watch.desktop' if watcher else 'bailong-linux.desktop')


def register_startup(enabled, watcher=False):
    path = startup_path(watcher)
    if not enabled:
        path.unlink(missing_ok=True)
        return
    command = app_command() + (['--watch-codex'] if watcher else [])
    # Desktop Entry Exec quoting differs from shell quoting.
    def quote(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
    text = '[Desktop Entry]\nType=Application\nName=白龙桌宠\nExec=' + ' '.join(map(quote, command)) + '\nTerminal=false\nX-GNOME-Autostart-enabled=true\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def desktop_sessions():
    import psutil
    sessions = set()
    uncertain = False
    for process in psutil.process_iter(['name']):
        try:
            if (process.info['name'] or '').lower() not in ('chatgpt', 'codex', 'codex-desktop'):
                continue
            executable = Path(process.exe())
            if not (executable.parent / 'resources/app.asar').is_file():
                continue  # Excludes the Codex CLI and its app-server.
            if any(arg.startswith('--type=') for arg in process.cmdline()[1:]):
                continue
            sessions.add((process.pid, process.create_time()))
        except psutil.AccessDenied:
            uncertain = True
        except (psutil.NoSuchProcess, OSError):
            pass
    return sessions if sessions or not uncertain else None


def open_codex(session=None):
    if session is not None:
        from desktop_services import codex_conversation_url
        target = codex_conversation_url(session)
        subprocess.Popen(['xdg-open', target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        executable = shutil.which('codex-gui')
        if not executable:
            raise OSError('未找到 Codex 桌面启动入口 codex-gui')
        subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def notify(title, text):
    tool = shutil.which('notify-send')
    if tool:
        subprocess.Popen([tool, '--app-name=白龙桌宠', '--hint=boolean:suppress-sound:true',
                          '--urgency=low', '--', title, text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class SecretStore:
    """Store chat provider keys in the desktop Secret Service, never plaintext."""
    def __init__(self, path):
        self.namespace = hashlib.sha256(str(Path(path).absolute()).encode()).hexdigest()

    def _run(self, arguments, value=None):
        tool = shutil.which('secret-tool')
        if not tool:
            raise OSError('需要桌面 Secret Service 和 secret-tool 才能安全保存聊天密钥')
        try:
            result = subprocess.run([tool] + arguments + ['application', 'bailong-linux', 'store', self.namespace],
                                    input=value, capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            raise OSError('桌面密钥环未响应，请先解锁密钥环') from None
        if result.returncode not in (0, 1):
            raise OSError('桌面密钥环操作失败')
        return result

    def get(self, name):
        result = self._run(['lookup', 'provider', str(name)])
        return result.stdout.rstrip('\n') if result.returncode == 0 else ''

    def put(self, name, value):
        if value:
            result = self._run(['store', '--label=白龙桌宠聊天服务', 'provider', str(name)], value)
            if result.returncode:
                raise OSError('桌面密钥环未保存密钥')
        else:
            self._run(['clear', 'provider', str(name)])


def watcher_main():
    import fcntl
    import json
    import time
    from codex_startup import LaunchGate, data_dir, enabled
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / 'codex-watch.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    gate = LaunchGate()
    launches = 0
    while enabled():
        if gate.observe(desktop_sessions()):
            subprocess.Popen(app_command() + ['--from-codex'], start_new_session=True)
            launches += 1
        path = root / 'codex-watch-state.json'
        path.write_text(json.dumps({'pid': os.getpid(), 'launches': launches, 'checked': time.time()}))
        time.sleep(2)
    lock.close()
    return 0


def start_watcher():
    from codex_startup import enabled
    if enabled():
        subprocess.Popen(app_command() + ['--watch-codex'], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ipc_listen(reader):
    """Use the current owner's Unix socket and the upstream framed protocol."""
    import select
    import socket
    import stat
    import msgspec
    from codex_connection import data_home
    candidates = [data_home() / 'ipc/ipc.sock', Path('/tmp/codex-ipc') / f'ipc-{os.getuid()}.sock']

    class Stream:
        def __init__(self, connection): self.connection = connection
        def read(self, size): return self.connection.recv(size)
        def write(self, data):
            self.connection.sendall(data)
            return len(data)

    while not reader.stop_event.is_set():
        try:
            connection = None
            for path in candidates:
                candidate = None
                try:
                    details = path.lstat()
                    if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.getuid():
                        continue
                    candidate = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    candidate.settimeout(2)
                    candidate.connect(str(path))
                except OSError:
                    if candidate is not None:
                        candidate.close()
                    continue
                connection = candidate
                break
            if connection is None:
                raise OSError('Codex IPC unavailable')
            with connection:
                def available():
                    if not select.select([connection], [], [], 0)[0]:
                        return 0
                    data = connection.recv(65536, socket.MSG_PEEK)
                    if not data:
                        raise OSError('Codex IPC disconnected')
                    return len(data)
                reader._listen(Stream(connection), available)
        except (OSError, ValueError, msgspec.MsgspecError):
            reader.set_health('degraded', 'ipc_disconnected')
        finally:
            reader.connected = False
        reader.stop_event.wait(5)
