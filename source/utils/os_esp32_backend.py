"""Input/screen backend that drives the mouse and keyboard through the ESP32 board.

Same functions as the original os_windows_backend (moveTo, click, dragTo,
press, ...) so the bot code calls it unchanged. Screen capture and window
lookups still use the Win32 API; only input goes through the board.

The board moves the pointer in absolute coordinates over the primary monitor,
so the game window has to be on the primary monitor.
"""

import ctypes
from ctypes import wintypes
import math
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np

import source.utils.params as p
from source.utils.profiles import get_macro_profile, maybe_rhythm_jitter, randomize_with_profile

_HOST = Path(__file__).resolve().parents[2] / "host"
if _HOST.is_dir() and str(_HOST) not in sys.path:
    sys.path.insert(0, str(_HOST))

from cg_esp32.device import DeviceError, Esp32Device  # noqa: E402
from cg_esp32 import motion  # noqa: E402


_device = None
_device_lock = threading.RLock()
_port = None  # last port the board answered on


def _close_device():
    global _device
    if _device is not None:
        try:
            _device.close()
        except Exception:
            pass
        _device = None


def _open(port=None):
    global _device, _port
    _device = Esp32Device(port)
    _port = _device.port
    return _device


def _get_device():
    """Open the board on first use; reopen it if the link was lost (e.g. replugged)."""
    with _device_lock:
        if _device is not None and not _device.alive:
            _close_device()
        if _device is None:
            try:
                _open(_port)
            except DeviceError:
                if _port is None:
                    raise
                _open(None)  # replugged onto another COM number
        return _device


def connect(port=None):
    """Open the board (on `port`, or the first Espressif port) and return it.

    Raises DeviceError when nothing answers. Closes any board opened before.
    """
    with _device_lock:
        _close_device()
        return _open(port)


def disconnect():
    """Close the board's port, e.g. so the flasher can use it."""
    with _device_lock:
        _close_device()


def current_device():
    """The open board, or None."""
    with _device_lock:
        return _device if _device is not None and _device.alive else None


def restore_mouse_settings():
    """Release anything the board still holds. Called on pause and on stop.

    The original used this to undo its pointer-speed changes; the ESP32 never
    touches Windows mouse settings, so letting go of buttons and keys is all
    that is left to do.
    """
    with _device_lock:
        dev = _device
    if dev is None or not dev.alive:
        return
    dev.release_all()
    dev.flush()


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD)
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3)
    ]

def screenshot(imageFilename=None, region=None, allScreens=False):
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    if allScreens:
        width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        x, y = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)  # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN
    else:
        width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        x = y = 0

    if region:
        x, y, rwidth, rheight = region
        width, height = rwidth, rheight
    else:
        region = (x, y, width, height)

    hdc = user32.GetDC(None)
    mfc_dc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mfc_dc, bitmap)

    gdi32.BitBlt(mfc_dc, 0, 0, width, height, hdc, x, y, 0x00CC0020)  # SRCCOPY

    try:
        bmpinfo = BITMAPINFO()
        bmpinfo.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmpinfo.bmiHeader.biWidth = width
        bmpinfo.bmiHeader.biHeight = -height
        bmpinfo.bmiHeader.biPlanes = 1
        bmpinfo.bmiHeader.biBitCount = 32
        bmpinfo.bmiHeader.biCompression = 0

        buffer_len = width * height * 4
        buffer = ctypes.create_string_buffer(buffer_len)
        gdi32.GetDIBits(mfc_dc, bitmap, 0, height, buffer, ctypes.byref(bmpinfo), 0)

        arr = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
        arr = arr[:, :, :3]  # Remove alpha channel

        if imageFilename:
            import cv2  # Will raise error if not available
            cv2.imwrite(imageFilename, arr)
        return arr

    finally:
        # Cleanup
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mfc_dc)
        user32.ReleaseDC(None, hdc)


user32 = ctypes.windll.user32

# Tweening functions
def linear(t):
    return t

def easeInOutQuad(t):
    return 2*t*t if t < 0.5 else -1 + (4 - 2*t)*t

def easeOutElastic(t):
    c4 = (2 * math.pi) / 3
    if t == 0:
        return 0
    elif t == 1:
        return 1
    return 2**(-10 * t) * math.sin((t * 10 - 0.75) * c4) + 1

# Helper functions
def get_screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

def get_position():
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y

def getActiveWindowTitle():
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value

def center(target=None):
    """
    Returns the center coordinates of:
    - A window (if target is a string title)
    - A screen region (if target is a box tuple (left, top, width, height))
    - The primary screen (if no target)
    """
    if isinstance(target, str):  # Window title
        hwnd = user32.FindWindowW(None, target)
        if not hwnd:
            raise ValueError(f"Window not found: {target}")
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (
            (rect.left + rect.right) // 2,
            (rect.top + rect.bottom) // 2
        )
    elif isinstance(target, (tuple, list)) and len(target) >= 4:  # Region box
        left, top, width, height = target[:4]
        return (left + width // 2, top + height // 2)
    else:  # Primary screen center
        width, height = get_screen_size()
        return (width // 2, height // 2)


def get_virtual_screen_bounds():
    """Bounds the bot may work in: the primary monitor, the only one the board reaches."""
    width, height = get_screen_size()
    return 0, 0, width, height


def clip_region_to_virtual(region):
    x, y, w, h = region
    min_x, min_y, max_x, max_y = p.SCREEN

    x2 = max(x, min_x)
    y2 = max(y, min_y)

    x_end = min(x + w, max_x)
    y_end = min(y + h, max_y)

    w2 = x_end - x2
    h2 = y_end - y2

    if w2 <= 0 or h2 <= 0:
        return None

    return x2, y2, w2, h2


def _human_delay(min_delay=0.01, max_delay=0.03):
    time.sleep(random.uniform(min_delay, max_delay))


def _profile_value(profile, key, default):
    if profile is None:
        return default
    return profile.get(key, default)


def _sample_hold_seconds(kind, profile=None):
    """Sample hold duration from median/IQR and clamp to profile bounds."""
    if kind == "click":
        median_ms = float(_profile_value(profile, "click_hold_median_ms", 90.0))
        iqr_ms = float(_profile_value(profile, "click_hold_iqr_ms", 18.0))
        min_ms, max_ms = _profile_value(profile, "click_hold_bounds_ms", (38.0, 220.0))
    else:
        median_ms = float(_profile_value(profile, "key_hold_median_ms", 100.0))
        iqr_ms = float(_profile_value(profile, "key_hold_iqr_ms", 31.0))
        min_ms, max_ms = _profile_value(profile, "key_hold_bounds_ms", (32.0, 260.0))

    sigma_ms = max(1.0, iqr_ms / 1.349)
    sampled_ms = random.gauss(median_ms, sigma_ms)
    sampled_ms = max(float(min_ms), min(float(max_ms), sampled_ms))
    return sampled_ms / 1000.0


def mouseDown(button='left', delay=0.16, jitter=0.04):
    _fail_safe_check()
    dev = _get_device()
    dev.button_down(button)
    dev.flush()
    if delay > 0:
        _human_delay(delay, delay + max(0.0, jitter))
    _fail_safe_check()


def mouseUp(button='left', delay=0.16, jitter=0.05):
    _fail_safe_check()
    dev = _get_device()
    dev.button_up(button)
    dev.flush()
    if delay > 0:
        _human_delay(delay, delay + max(0.0, jitter))
    _fail_safe_check()


class WindowError(Exception): pass
class FailSafeException(Exception): pass
class ImageNotFoundException(Exception): pass
class PauseException(Exception):
    def __init__(self, name):
        super().__init__(name)
        self.window = name

# Global fail-safe settings
FAILSAFE_ENABLED = True


def _apply_macro_rhythm(profile=None):
    profile = profile or get_macro_profile()
    pause, (dx, dy) = maybe_rhythm_jitter(profile)

    if dx != 0 or dy != 0:
        dev = _get_device()
        dev.move_by(dx, dy)
        dev.flush()
        _human_delay(0.004, 0.012)

    if pause > 0:
        time.sleep(pause)

    _fail_safe_check()

def set_failsafe(state=True):
    """Enable or disable the fail-safe feature"""
    global FAILSAFE_ENABLED
    FAILSAFE_ENABLED = state


def _fail_safe_check():
    """Pause when the game is no longer the foreground window."""
    if not FAILSAFE_ENABLED:
        return

    name = getActiveWindowTitle()

    if p.LIMBUS_NAME not in name:
        restore_mouse_settings()
        raise PauseException(name)


def _clamp_point_to_screen_bounds(x, y):
    min_x, min_y, max_x, max_y = p.SCREEN or get_virtual_screen_bounds()
    max_x = max(min_x, max_x - 1)
    max_y = max(min_y, max_y - 1)
    return (
        int(round(min(max(float(x), min_x), max_x))),
        int(round(min(max(float(y), min_y), max_y))),
    )


def moveTo(x, y, duration=0, delay=0.0, tsize=(5.0, 5.0), offset_x=0, offset_y=0, curve=1, n_sub=None, inertia=False):
    _fail_safe_check()

    end_x, end_y = _clamp_point_to_screen_bounds(x + offset_x, y + offset_y)
    tsize = tsize if tsize else (20.0, 20.0)
    if motion._within(get_position(), (end_x, end_y), tsize):
        return

    if delay > 0:
        profile = get_macro_profile()
        time.sleep(randomize_with_profile(delay, profile=profile, key="delay_jitter"))

    motion.move(
        _get_device(), end_x, end_y,
        duration=duration if duration and duration > 0 else None,
        target_size=tsize,
        curve=curve,
        n_sub=n_sub,
        inertia=inertia,
    )
    _fail_safe_check()


def click(x=None, y=None, button='left', clicks=1, interval=0.15, duration=0.0, tsize=(5.0, 5.0), delay=0.03):
    _fail_safe_check()
    profile = get_macro_profile()
    _apply_macro_rhythm(profile)
    delay = randomize_with_profile(delay, profile=profile, key="delay_jitter")

    if x is not None and y is not None:
        moveTo(x, y, duration=duration, delay=delay+0.02, tsize=tsize)

    for i in range(clicks):
        _fail_safe_check()
        click_hold = _sample_hold_seconds("click", profile=profile)
        mouseDown(button, delay=click_hold, jitter=0.0)
        mouseUp(button, delay=delay)

        if interval > 0 and i < clicks - 1:
            time.sleep(randomize_with_profile(interval, profile=profile, key="click_interval_jitter"))
            _fail_safe_check()


def dragTo(x, y, duration=0.1, button='left', tsize=(5.0, 5.0), start_x=None, start_y=None, hook=False):
    _fail_safe_check()
    _apply_macro_rhythm()

    if start_x is not None and start_y is not None:
        moveTo(start_x, start_y, tsize=tsize)

    mouseDown(button, delay=0.03)
    moveTo(x, y, duration=duration, tsize=tsize, n_sub=1, curve=0.2, inertia=False)
    mouseUp(button, delay=0.03)

    if hook:
        mouseDown(button, delay=0.03)
        mouseUp(button, delay=0.03)
    _fail_safe_check()

def scroll(clicks, x=None, y=None):
    _fail_safe_check()
    _apply_macro_rhythm()
    if x is not None and y is not None:
        moveTo(x, y)

    dev = _get_device()
    direction = 1 if clicks > 0 else -1
    count = abs(int(clicks))
    for _ in range(count):
        _fail_safe_check()
        dev.scroll(direction)
        dev.flush()
        time.sleep(0.02)
    _human_delay()


def press(keys, presses=1, interval=0.1, delay=0.09):
    profile = get_macro_profile()
    _apply_macro_rhythm(profile)
    time.sleep(randomize_with_profile(delay, profile=profile, key="delay_jitter"))

    if isinstance(keys, str):
        keys = [keys]

    dev = _get_device()
    for _p in range(presses):
        for key in keys:
            _fail_safe_check()
            dev.key_down(key)
            dev.flush()
            key_hold = _sample_hold_seconds("key", profile=profile)
            time.sleep(key_hold)

        for key in reversed(keys):
            dev.key_up(key)
        dev.flush()

        if interval > 0 and _p < presses - 1:
            time.sleep(randomize_with_profile(interval, profile=profile, key="key_interval_jitter"))
            _fail_safe_check()

def hotkey(*args, **kwargs):
    press(list(args), **kwargs)


def check_window():
    min_x, min_y, max_x, max_y = p.SCREEN
    left, top, width, height = p.WINDOW
    in_bounds = (
        left >= min_x and
        top >= min_y and
        left + width <= max_x and
        top + height <= max_y
    )
    if not in_bounds:
        raise WindowError("The game window must be fully on the primary monitor (the ESP32 can only reach that one).")

def set_window():
    hwnd = ctypes.windll.user32.FindWindowW(None, p.LIMBUS_NAME)

    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))

    pt = ctypes.wintypes.POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))

    client_width = rect.right - rect.left
    client_height = rect.bottom - rect.top
    left, top = pt.x, pt.y

    target_ratio = 16 / 9
    if client_width / client_height > target_ratio:
        target_height = client_height
        target_width = int(target_height * target_ratio)
    elif client_width / client_height < target_ratio:
        target_width = client_width
        target_height = int(target_width / target_ratio)
    else:
        target_width = client_width
        target_height = client_height

    left += (client_width - target_width) // 2
    top += (client_height - target_height) // 2

    p.WINDOW = (left, top, target_width, target_height)
    p.SCREEN = get_virtual_screen_bounds()
    check_window()

    if int(client_width / 16) != int(client_height / 9):
        p.WARNING(f"Game window ({client_width} x {client_height}) is not 16:9\nIt is recommended to set the game to either\n1920 x 1080 or 1280 x 720")

    print("WINDOW:", p.WINDOW)
