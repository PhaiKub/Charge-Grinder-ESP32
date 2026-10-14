"""Keeps the board open for the bot and rides out an unplugged cable.

The bot sends every input through BoardKeeper.run(). When the board drops out
(DeviceLost), run() tells the app, waits until the board answers again, and
repeats the step that failed, so a loose cable pauses the bot instead of
stopping it with an error.
"""

import threading
import time

from .base import DeviceLost


class WaitCancelled(Exception):
    """The wait for a lost board was called off (the user stopped the bot)."""


class BoardKeeper:
    """Holds the open board and reopens it after a replug.

    `open_device(port)` opens a board and returns it (port None: find one);
    it raises DeviceLost when nothing answers. `present()` says whether a
    board's port is on the bus; it is checked before each open attempt while
    waiting, so a missing board costs no serial timeout.
    """

    def __init__(self, open_device, *, present=lambda: True, poll=1.0, settle=1.0, sleep=time.sleep):
        self._open_device = open_device
        self._present = present
        self._poll = poll
        self._settle = settle
        self._sleep = sleep
        self.lock = threading.RLock()
        self.device = None
        self.port = None  # last port the board answered on
        # Set by the app while the bot runs. Without on_lost, run() raises
        # DeviceLost straight away instead of waiting.
        self.on_lost = None       # fn(reason) once the board is gone
        self.on_back = None       # fn(device) once it answers again
        self.cancelled = lambda: False

    # ── Open / close ──────────────────────────────────────────────────────────

    def _close(self):
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def _adopt(self, dev, port=None):
        self.device = dev
        self.port = getattr(dev, "port", None) or port
        return dev

    def _open_any(self):
        try:
            return self._open_device(self.port)
        except DeviceLost:
            if self.port is None:
                raise
            return self._open_device(None)  # replugged onto another COM number

    @staticmethod
    def _alive(dev):
        return dev is not None and getattr(dev, "alive", True)

    def get(self):
        """The open board; opens it, or reopens it after it was lost."""
        with self.lock:
            if self.device is not None and not self._alive(self.device):
                self._close()
            if self.device is None:
                self._adopt(self._open_any())
            return self.device

    def connect(self, port=None):
        """Close any open board, then open the one on `port` (None: find one)."""
        with self.lock:
            self._close()
            return self._adopt(self._open_device(port), port)

    def disconnect(self):
        with self.lock:
            self._close()

    def current(self):
        """The open board, or None. Never blocks (the UI polls it)."""
        dev = self.device
        return dev if self._alive(dev) else None

    # ── Riding out an unplug ──────────────────────────────────────────────────

    def run(self, op):
        """Return op(board). If the board drops out, wait for it and run op again."""
        while True:
            try:
                return op(self.get())
            except DeviceLost as exc:
                if self.on_lost is None:
                    raise
                self.wait(str(exc))

    def wait(self, reason):
        """Block until a board answers again; raises WaitCancelled if cancelled first."""
        with self.lock:
            self._close()
        self.on_lost(reason)
        while True:
            if self.cancelled():
                raise WaitCancelled(reason)
            if self._present():
                try:
                    # Opened outside the lock: a board that is on the bus but
                    # not answering yet takes a whole reply timeout.
                    dev = self._open_any()
                    with self.lock:
                        self._close()
                        self._adopt(dev)
                    dev.release_all()  # nothing stays held from before the drop
                    dev.flush()
                except DeviceLost:
                    with self.lock:
                        self._close()
                else:
                    self._sleep(self._settle)
                    if self.cancelled():
                        raise WaitCancelled(reason)
                    if self.on_back is not None:
                        self.on_back(dev)
                    return dev
            self._sleep(self._poll)
