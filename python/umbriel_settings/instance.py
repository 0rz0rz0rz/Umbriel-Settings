"""One app window per user: a second launch hands its config path to the running app and exits.

Two windows would share one draft file (the last one closed would overwrite the other's draft) and could
save over each other, so the running window is raised instead.
"""

import fcntl
import json
import os
import sys
import tempfile

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def socket_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(runtime, f"umbriel-settings-{os.getuid()}.sock")


def hand_over(message, path=None, timeout_ms=1000):
    """Send `message` to a running app; False when none answers (then this process becomes the app)."""
    socket = QLocalSocket()
    socket.connectToServer(path or socket_path())
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(json.dumps(message).encode("utf-8"))
    socket.flush()
    if socket.bytesToWrite():
        socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True  # an app is running even if the message got lost; a second window must not start


class InstanceServer(QObject):
    """Listens for later launches; emits `activated` with each launch's message (a dict)."""

    activated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)

    def listen(self, path=None):
        path = path or socket_path()
        QLocalServer.removeServer(path)  # left behind by an app that crashed; nobody answered on it
        return self.server.listen(path)

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.setParent(self)
            chunks = []
            socket.readyRead.connect(lambda s=socket, c=chunks: c.append(bytes(s.readAll().data())))
            socket.disconnected.connect(lambda s=socket, c=chunks: self._finish(s, c))

    def _finish(self, socket, chunks):
        chunks.append(bytes(socket.readAll().data()))
        socket.deleteLater()
        try:
            message = json.loads(b"".join(chunks).decode("utf-8") or "{}")
        except (UnicodeError, ValueError):
            return
        if isinstance(message, dict):
            self.activated.emit(message)


def claim(message, path=None):
    """Return an InstanceServer when this process is the app, or None after handing over to a running one.
    Asking and listening happen under a lock: Qt's listen replaces any socket file, so of two launches at once
    the second would otherwise take the socket from the first and both would open a window."""
    path = path or socket_path()
    with open(path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if hand_over(message, path):
            return None
        server = InstanceServer()
        if not server.listen(path):
            print(f"Umbriel Settings: single-instance socket unavailable: {server.server.errorString()}",
                  file=sys.stderr)
        return server
