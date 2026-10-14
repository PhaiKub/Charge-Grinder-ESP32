"""Board page inside the main window: find the board, show its status, switch
its LED and flash its firmware.

It covers the main window below the title bar, like the Bot Config page, and
uses the same look: dark panels, bronze borders, parchment text, cyan accents
and the ExcelsiorSans font. At startup the app scans in the background and
only opens the page when something is wrong (no board, or no answer); a
firmware update just turns the BOARD button gold. The BOARD button in the
title bar opens and closes it.
"""

import os
import threading

from PySide6.QtCore import QLocale, QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
    QSizePolicy, QVBoxLayout,
)

import source.utils.os_esp32_backend as backend
from source.utils.paths import BASE_PATH

from cg_esp32 import boards, flasher
from cg_esp32.device import DeviceError, DeviceRejected

FIRMWARE_DIST = os.path.join(BASE_PATH, "firmware", "dist")
LED_FIRMWARE = (0, 3, 0)  # first firmware with SET_LED

# Main window palette (App.py)
TEXT = "#EDD1AC"
MUTED = "#bfa37e"
ACCENT = "#5df2ff"
BRONZE = "#7B6240"
GOLD = "#f2c46d"
ERROR = "#FF8080"

STYLE = f"""
QFrame#devicePanel {{ background-color: rgba(9, 9, 9, 242); }}
QLabel {{ color: {TEXT}; background: transparent; border: none; }}
QLabel#muted {{ color: {MUTED}; }}
QFrame#box {{
    background-color: rgba(0, 0, 0, 205);
    border: 1px solid {BRONZE};
    border-radius: 6px;
}}
QFrame#box[tone="error"] {{
    background-color: rgba(64, 12, 12, 225);
    border: 1px solid #a04646;
}}
QFrame#box[tone="ok"] {{
    background-color: rgba(17, 61, 70, 160);
    border: 1px solid {ACCENT};
}}
QPlainTextEdit {{
    color: {TEXT};
    background: transparent;
    border: none;
    selection-background-color: #1f7380;
}}
QPushButton {{
    color: {TEXT};
    background-color: rgba(0, 0, 0, 205);
    border: 1px solid {BRONZE};
    border-radius: 4px;
    padding: 3px 12px;
}}
QPushButton:hover {{ color: {ACCENT}; border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: #6b5a45; border: 1px solid #3d3122; }}
QPushButton#primary {{
    color: {ACCENT};
    background-color: rgba(17, 61, 70, 205);
    border: 1px solid {ACCENT};
}}
QPushButton#primary:disabled {{
    color: #3f6f74;
    background-color: rgba(0, 0, 0, 205);
    border: 1px solid #23474b;
}}
QPushButton#flash {{ color: {GOLD}; border: 1px solid #b8893a; }}
QPushButton#flash:hover {{ color: #ffe2a3; border: 1px solid {GOLD}; }}
QPushButton#flash:disabled {{ color: #6b5a45; border: 1px solid #3d3122; }}
QPushButton#icon {{ padding: 2px; min-width: 30px; max-width: 30px; }}
QPushButton#toggle {{ color: {MUTED}; padding: 2px 10px; }}
QPushButton#toggle:checked {{
    color: {ACCENT};
    background-color: rgba(17, 61, 70, 205);
    border: 1px solid {ACCENT};
}}
QPushButton#toggle:disabled {{
    color: #6b5a45;
    background-color: rgba(0, 0, 0, 205);
    border: 1px solid #3d3122;
}}
QComboBox {{
    color: {ACCENT};
    background-color: rgba(0, 0, 0, 220);
    border: 1px solid #d3c19b;
    border-radius: 4px;
    padding: 3px 8px;
}}
QComboBox:disabled {{ color: #6b5a45; border: 1px solid #3d3122; }}
QComboBox QAbstractItemView {{
    color: {TEXT};
    background-color: #110e0b;
    border: 1px solid {BRONZE};
    selection-background-color: #1f7380;
    outline: none;
}}
QProgressBar {{
    color: {TEXT};
    background-color: rgba(0, 0, 0, 220);
    border: 1px solid {BRONZE};
    border-radius: 4px;
    text-align: center;
    min-height: 20px;
}}
QProgressBar::chunk {{ background-color: #1f7380; border-radius: 3px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BRONZE}; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QToolTip {{ color: {TEXT}; background-color: #110e0b; border: 1px solid {BRONZE}; }}
"""

# Header per state: symbol, colour
STATES = {
    "scanning": ("⟳", ACCENT),
    "connected": ("✔", ACCENT),
    "update": ("⚡", GOLD),
    "not_found": ("✖", ERROR),
    "flashing": ("⚡", GOLD),
    "flashed": ("✔", ACCENT),
    "flash_failed": ("✖", ERROR),
    "busy": ("●", MUTED),
}


class _Signals(QObject):
    line = Signal(str)
    progress = Signal(int)
    scan_done = Signal(object)    # Esp32Device or None
    flash_done = Signal(object)   # None on success, error text on failure


class DevicePanel(QFrame):
    """The device page. `family` is the main window's font; `is_busy()` says
    whether the bot is running (then the page only shows the status, since
    connecting or flashing would pull the board from under it).

    `changed` fires whenever the connection may have changed, so the status
    dot can refresh.
    """

    changed = Signal()

    def __init__(self, parent, *, family, is_busy):
        super().__init__(parent)
        self.setObjectName("devicePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._is_busy = is_busy
        self.busy = False
        self.device = backend.current_device()
        self._working = False
        self._quiet = False        # scanning in the background at startup
        self._auto_hide = False    # hide again once a board with current firmware answers
        self.update_ready = False  # the app has newer firmware than the board
        self._refresh_buttons = []
        self._ports = {}
        self._settings = QSettings("Charge-Grinder-ESP32", "device")
        self._signals = _Signals()
        self._signals.line.connect(self._log)
        self._signals.progress.connect(self._on_progress)
        self._signals.scan_done.connect(self._on_scan_done)
        self._signals.flash_done.connect(self._on_flash_done)
        self._font = lambda size: QFont(family or self.font().family(), size)

        self.setStyleSheet(STYLE)
        self.setLocale(QLocale(QLocale.Language.English))  # "100%", not the system's digits
        self._build()
        self._show_led()

        saved = self._settings.value("board", boards.DEFAULT_BOARD.id)
        index = next((i for i, b in enumerate(boards.BOARDS) if b.id == saved), 0)
        self.board_combo.setCurrentIndex(index)
        self._on_board_changed(index)
        self.hide()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 16, 34, 22)
        root.setSpacing(10)

        # Header
        self.symbol = QLabel()
        self.symbol.setFont(self._font(24))
        self.title = QLabel()
        self.title.setFont(self._font(24))
        header = QHBoxLayout()
        header.addStretch()
        header.addWidget(self.symbol)
        header.addSpacing(6)
        header.addWidget(self.title)
        header.addStretch()
        root.addLayout(header)
        self.subtitle = self._label("", 13, muted=True, wrap=True)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.subtitle)

        # Message / log box
        self.message_box = self._box()
        box = QVBoxLayout(self.message_box)
        box.setContentsMargins(10, 6, 10, 6)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setFixedHeight(104)
        box.addWidget(self.log)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setLocale(QLocale(QLocale.Language.English))
        self.progress.setFont(self._font(12))
        self.progress.hide()
        box.addWidget(self.progress)
        self.message_box.hide()  # shown once there is something to log
        root.addWidget(self.message_box)

        # Board + status
        info = self._box()
        grid = QVBoxLayout(info)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setSpacing(4)
        row = QHBoxLayout()
        row.addWidget(self._label("Board", 16))
        self.board_combo = QComboBox()
        self.board_combo.setFont(self._font(14))
        for board in boards.BOARDS:
            self.board_combo.addItem(board.name, board.id)
        self.board_combo.currentIndexChanged.connect(self._on_board_changed)
        row.addWidget(self.board_combo, 1)
        grid.addLayout(row)
        self.ports_help = self._label("", 12, muted=True, wrap=True)
        grid.addWidget(self.ports_help)
        self.status_line = self._label("", 14, wrap=True)
        grid.addWidget(self.status_line)
        self.firmware_line = self._label("", 14, wrap=True)
        grid.addWidget(self.firmware_line)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._label("Status LED", 14))
        self.led_btn = self._button("", self._toggle_led, name="toggle")
        self.led_btn.setCheckable(True)
        self.led_btn.setFixedWidth(70)
        self.led_btn.setToolTip("The light on the board. The board remembers this setting.")
        row.addWidget(self.led_btn)
        self.led_note = self._label("", 12, muted=True)
        row.addWidget(self.led_note, 1)
        grid.addLayout(row)
        root.addWidget(info)

        # Bot port row
        self.usb_combo = QComboBox()
        self.connect_btn = self._button("Connect", self.connect_selected, primary=True)
        self.scan_btn = self._button("Re-scan", self.scan)
        root.addLayout(self._port_row(ACCENT, "Bot port", self.usb_combo,
                                      [self.connect_btn, self.scan_btn]))

        # Flash port row
        self.flash_combo = QComboBox()
        self.flash_btn = self._button("⚡ Flash Firmware", self.flash, name="flash")
        self.flash_label = QLabel()
        root.addLayout(self._port_row(GOLD, "Flash port", self.flash_combo, [self.flash_btn],
                                      label_widget=self.flash_label))

        self.hint = self._label("", 12, muted=True, wrap=True)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.hint)
        root.addStretch()

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.close_btn = self._button("Close Panel", self.hide_panel)
        self.close_btn.setFont(self._font(16))
        bottom.addWidget(self.close_btn)
        root.addLayout(bottom)

    def _box(self):
        frame = QFrame()
        frame.setObjectName("box")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        return frame

    def _label(self, text, size, *, muted=False, wrap=False):
        label = QLabel(text)
        label.setFont(self._font(size))
        if muted:
            label.setObjectName("muted")
        label.setWordWrap(wrap)
        return label

    def _button(self, text, handler, *, primary=False, name=None):
        button = QPushButton(text)
        button.setFont(self._font(14))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            button.setObjectName("primary")
        if name:
            button.setObjectName(name)
        button.clicked.connect(handler)
        return button

    def _port_row(self, colour, text, combo, buttons, label_widget=None):
        row = QHBoxLayout()
        row.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {colour};")
        row.addWidget(dot)
        label = label_widget or QLabel()
        label.setText(text)
        label.setFont(self._font(15))
        label.setFixedWidth(88)
        row.addWidget(label)
        combo.setFont(self._font(13))
        combo.setMinimumWidth(170)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(combo, 1)
        refresh = self._button("⟳", self._refresh_ports, name="icon")
        refresh.setToolTip("Refresh the port list")
        self._refresh_buttons.append(refresh)
        row.addWidget(refresh)
        for button in buttons:
            row.addWidget(button)
        return row

    def paintEvent(self, event):
        # Bronze double frame, like the main window's panels.
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(BRONZE), 2))
        painter.drawRoundedRect(self.rect().adjusted(14, 4, -15, -8), 8, 8)
        painter.setPen(QPen(QColor("#3a2c1b"), 1))
        painter.drawRoundedRect(self.rect().adjusted(19, 9, -20, -13), 6, 6)

    # ── Open / close ──────────────────────────────────────────────────────────

    def open_panel(self):
        """Show the page; scan if no board is connected."""
        self.busy = self._is_busy()
        self.device = backend.current_device()
        self._quiet = False
        self._auto_hide = False
        self._refresh_ports()
        if self.busy:
            self._set_state("busy", "Bot is running", "Stop the bot to connect again or flash firmware.")
        elif self.device is not None and not self._working:
            self._after_connect(self.device)
        self.show()
        self.raise_()
        if self.device is None and not self.busy and not self._working:
            self.scan()

    def hide_panel(self):
        if self._working:
            return
        self.hide()
        self.changed.emit()

    def toggle_panel(self):
        if self.isVisible():
            self.hide_panel()
        else:
            self.open_panel()

    def startup_scan(self):
        """Look for the board without showing the page; the page opens only
        if the board is missing or its firmware is out of date."""
        self._quiet = True
        self._auto_hide = True
        self.scan()

    # ── State ─────────────────────────────────────────────────────────────────

    @property
    def board(self) -> boards.Board:
        return boards.BOARDS[max(self.board_combo.currentIndex(), 0)]

    def _image(self):
        return boards.find_image(self.board, FIRMWARE_DIST)

    def _set_state(self, state, title, subtitle="", tone=None):
        symbol, colour = STATES[state]
        self.symbol.setText(symbol)
        self.symbol.setStyleSheet(f"color: {colour};")
        self.title.setText(title)
        self.title.setStyleSheet(f"color: {colour if state in ('not_found', 'flash_failed') else TEXT};")
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        self.message_box.setProperty("tone", tone or "")
        self.message_box.style().unpolish(self.message_box)
        self.message_box.style().polish(self.message_box)
        self._update_controls()

    def _update_controls(self):
        idle = not self._working and not self.busy
        for widget in (self.board_combo, self.usb_combo, self.flash_combo, self.scan_btn,
                       *self._refresh_buttons):
            widget.setEnabled(idle)
        self.connect_btn.setEnabled(idle and self.usb_combo.count() > 0)
        self.flash_btn.setEnabled(idle and self.flash_combo.count() > 0 and self._image() is not None)
        self.close_btn.setEnabled(not self._working)
        self._update_status_lines()

    def _update_status_lines(self):
        dev = self.device
        if dev is not None:
            self.status_line.setText(f"Connected on {dev.port}  ·  screen {dev.screen_w}×{dev.screen_h}")
            self.status_line.setStyleSheet(f"color: {ACCENT};")
        else:
            self.status_line.setText("Not connected")
            self.status_line.setStyleSheet(f"color: {MUTED};")

        image = self._image()
        on_board = dev.firmware_version if dev is not None else None
        parts = []
        if on_board:
            parts.append(f"Firmware on board: {on_board}")
        if image is not None:
            parts.append(f"App has: {image.version}")
            if on_board and boards.is_newer(image.version, on_board):
                parts.append("update available")
        else:
            parts.append("No firmware image for this board (build it: pio run)")
        self.firmware_line.setText("  ·  ".join(parts))
        self.firmware_line.setStyleSheet(
            f"color: {GOLD};" if on_board and image and boards.is_newer(image.version, on_board) else "")

    def _clear_log(self, progress=False):
        self.log.clear()
        self.progress.setVisible(progress)
        self.message_box.setVisible(progress)

    def _log(self, text, error=False):
        self.message_box.show()
        colour = ERROR if error else TEXT
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.log.appendHtml(f'<span style="color:{colour}">{safe}</span>')

    def _reveal(self):
        """Show the page after a background scan that needs the user."""
        self._quiet = False
        self._auto_hide = False
        if not self.isVisible():
            self.show()
            self.raise_()

    # ── Board and ports ───────────────────────────────────────────────────────

    def _on_board_changed(self, index):
        board = self.board
        self._settings.setValue("board", board.id)
        self.ports_help.setText(board.ports_help)
        self.flash_label.setText("COM port" if board.two_ports else "Flash port")
        self.hint.setText(board.flash_help)
        self._refresh_ports()

    def _refresh_ports(self):
        ports = boards.list_ports()
        keep_usb = self.usb_combo.currentData()
        keep_flash = self.flash_combo.currentData()
        self._ports = {p.device: p for p in ports}

        def fill(combo, preferred_kind, keep, choices):
            combo.blockSignals(True)
            combo.clear()
            for port in choices:
                combo.addItem(port.label, port.device)
            target = keep if any(p.device == keep for p in choices) else next(
                (p.device for p in choices if p.kind == preferred_kind), choices[0].device if choices else None)
            if target is not None:
                combo.setCurrentIndex(combo.findData(target))
            combo.blockSignals(False)

        # The bot never runs over a UART bridge, and opening one resets the chip.
        fill(self.usb_combo, "native", keep_usb, [p for p in ports if p.kind != "uart"])
        fill(self.flash_combo, "uart" if self.board.two_ports else "native", keep_flash, ports)
        if self.device is not None:
            index = self.usb_combo.findData(self.device.port)
            if index >= 0:
                self.usb_combo.setCurrentIndex(index)
        self._update_controls()

    # ── Connect ───────────────────────────────────────────────────────────────

    def scan(self):
        self._start_scan(None)

    def connect_selected(self):
        port = self.usb_combo.currentData()
        if port:
            self._start_scan(port)

    def _start_scan(self, port):
        if self._working or self.busy:
            return
        self._working = True
        self.device = None
        self.update_ready = False
        self._clear_log()
        what = f"Connecting on {port}..." if port else "Scanning for the board..."
        self._set_state("scanning", what)
        last = self._settings.value("port")
        threading.Thread(target=self._scan_task, args=(port, last), daemon=True).start()

    def _scan_task(self, port, last):
        emit = self._signals.line.emit
        backend.disconnect()
        if port:
            candidates = [port]
        else:
            candidates = [p.device for p in boards.list_ports() if p.kind == "native"]
            if last in candidates:
                candidates.remove(last)
                candidates.insert(0, last)
            if not candidates:
                emit("No Espressif USB port found.")
        for device in candidates:
            emit(f"Trying {device}...")
            try:
                dev = backend.connect(device)
            except DeviceError as exc:
                emit(f"{device}: {exc}")
                continue
            emit(f"{device}: firmware {dev.firmware_version}"
                 + (f" ({dev.firmware_board})" if dev.firmware_board else ""))
            self._signals.scan_done.emit(dev)
            return
        self._signals.scan_done.emit(None)

    def _on_scan_done(self, dev):
        self._working = False
        self.device = dev
        self._refresh_ports()
        self.changed.emit()
        if dev is None:
            if not any(p.kind == "native" for p in self._ports.values()):
                why = ("The board's USB (native) port isn't plugged in. Plug it in, then Re-scan."
                       if self.board.two_ports else
                       "No board on USB. Plug it in, then Re-scan.")
            else:
                why = ("No board answered. Check the USB cable and that the "
                       "Charge-Grinder-ESP32 firmware is flashed.")
            self._set_state("not_found", "Board Not Found", why, tone="error")
            self._reveal()
            return
        self._settings.setValue("port", dev.port)
        matched = boards.board_for_firmware(dev.firmware_board, self.board)
        if matched is not None and matched is not self.board:
            self.board_combo.setCurrentIndex(boards.BOARDS.index(matched))
        self._after_connect(dev)

    def _after_connect(self, dev):
        self._apply_led(dev)
        image = self._image()
        self.update_ready = image is not None and boards.is_newer(image.version, dev.firmware_version)
        self.changed.emit()
        if self.update_ready:
            self._set_state("update", "Firmware Update Available",
                            f"The board runs {dev.firmware_version}; the app has {image.version}. "
                            "The bot still works; flash when convenient.", tone="ok")
            # Not a problem, so a startup scan leaves the main page up and only
            # the BOARD button turns gold.
            self._quiet = self._auto_hide = False
            return
        self._set_state("connected", "Board Connected",
                        f"{dev.port}  ·  firmware {dev.firmware_version}", tone="ok")
        if self._auto_hide:
            self._auto_hide = False
            if self._quiet:
                self._quiet = False
            else:
                QTimer.singleShot(700, self.hide_panel)

    # ── Status LED ────────────────────────────────────────────────────────────

    def _led_on(self):
        return self._settings.value("led", True, type=bool)

    def _show_led(self):
        on = self._led_on()
        self.led_btn.blockSignals(True)
        self.led_btn.setChecked(on)
        self.led_btn.blockSignals(False)
        self.led_btn.setText("ON" if on else "OFF")

    def _toggle_led(self, checked):
        self._settings.setValue("led", bool(checked))
        self._show_led()
        self._apply_led(self.device)

    def _apply_led(self, dev):
        """Send the saved LED setting to the board (it keeps it in flash)."""
        self.led_btn.setEnabled(True)
        self.led_note.setToolTip("")
        if dev is None:
            self.led_note.setText("Applied when the board connects")
            return
        # Older firmware rejects the command; checked first so a rejection can't
        # land on the bot's next command while it runs.
        if boards.version_tuple(dev.firmware_version) < LED_FIRMWARE:
            self.led_btn.setEnabled(False)
            image = self._image()
            if image is not None and boards.version_tuple(image.version) >= LED_FIRMWARE:
                self.led_note.setText("Needs firmware 0.3.0+: press Flash Firmware")
            else:
                self.led_note.setText("Needs firmware 0.3.0+: rebuild it (pio run), then flash")
            return
        on = self._led_on()
        try:
            dev.set_led(on)
        except DeviceRejected:
            self.led_note.setText("This firmware can't switch it: flash the firmware")
        except DeviceError as exc:
            self.led_note.setText("Couldn't reach the board")
            self.led_note.setToolTip(str(exc))
        else:
            self.led_note.setText(f"Board switched it {'on' if on else 'off'}")

    # ── Flash ─────────────────────────────────────────────────────────────────

    def flash(self):
        if self._working or self.busy:
            return
        image = self._image()
        port = self.flash_combo.currentData()
        if image is None or not port:
            return
        kind = self._ports[port].kind if port in self._ports else "other"
        self._working = True
        self.device = None
        self.update_ready = False
        self.changed.emit()
        self.progress.setValue(0)
        self._clear_log(progress=True)
        self._set_state("flashing", "Flashing Firmware",
                        f"{self.board.name}  ·  {image.version}  →  {port}. Don't unplug the board.")
        # A UART bridge resets the chip into download mode by itself. Over the
        # native USB port the app restarts the board into download mode first
        # (one cable is enough); a board already there (BOOT + RST) just stays.
        reset = kind == "uart"
        threading.Thread(target=self._flash_task, args=(port, image, reset), daemon=True).start()

    def _flash_task(self, port, image, reset):
        backend.disconnect()  # frees the port if the bot's connection held it
        try:
            if not reset:
                port = flasher.enter_download_mode(
                    port, list_native=lambda: [p.device for p in boards.list_ports() if p.kind == "native"],
                    on_line=self._signals.line.emit)
            flasher.flash(port, str(image.path), image.chip, reset=reset,
                          on_line=self._signals.line.emit, on_progress=self._signals.progress.emit)
        except flasher.FlashError as exc:
            self._signals.flash_done.emit(str(exc))
            return
        self._signals.flash_done.emit(None)

    def _on_progress(self, value):
        self.progress.setValue(value)

    def _on_flash_done(self, error):
        self._working = False
        if error:
            self._log(error, error=True)
            self._set_state("flash_failed", "Flash Failed", self._flash_advice(error), tone="error")
            return
        self.progress.setValue(100)
        if self.board.two_ports:
            note = "The board is restarting. Reconnecting..."
        else:
            note = "Press RST on the board if it doesn't restart by itself. Reconnecting..."
        self._set_state("flashed", "Firmware Flashed", note, tone="ok")
        QTimer.singleShot(3000, self.scan)

    def _flash_advice(self, error):
        text = error.lower()
        if "access is denied" in text or "permission" in text or "busy" in text:
            return "The port is in use. Close other serial tools (Arduino, PlatformIO monitor) and retry."
        if "did not come back" in text:
            return ("The board didn't restart into download mode. Put it there by hand: "
                    "hold BOOT, press and release RST, release BOOT. Re-scan, then Flash again.")
        if "wrong boot mode" in text or "failed to connect" in text or "no serial data" in text:
            if self.board.two_ports:
                return "The chip didn't enter download mode. Hold BOOT while you press Flash Firmware."
            return "The board isn't in download mode. " + self.board.flash_help
        if "this chip is" in text:
            return "This firmware is for a different chip. Pick the right board above."
        return "See the log above. Check the cable and the selected port, then retry."


class DeviceStatusButton(QPushButton):
    """"BOARD" button in the title bar, styled like the LOG button next to it:
    cyan when the board is connected, gold when a firmware update is waiting,
    red when not connected. Click to open or close
    the device page."""

    STYLE = ("QPushButton {{ color: {fg}; background-color: {bg}; border: 2px solid {edge};"
             " border-radius: 4px; padding: 0; }}"
             "QPushButton:hover {{ color: #ffffff; border: 2px solid {fg}; }}")

    def __init__(self, parent, on_click, family=None, has_update=lambda: False):
        super().__init__("BOARD", parent)
        self._has_update = has_update
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont(family or self.font().family(), 15))
        self.clicked.connect(on_click)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(2000)
        self.refresh()

    def refresh(self):
        dev = backend.current_device()
        if dev is not None and self._has_update():
            colours = dict(fg=GOLD, bg="#3a2a0a", edge="#b8893a")
            tip = f"Board connected on {dev.port}. Firmware update available: click to flash it."
        elif dev is not None:
            colours = dict(fg="#3fd8f2", bg="#0a2f3b", edge="#1597ad")
            tip = f"Board connected on {dev.port}, firmware {dev.firmware_version}. Click for the board page."
        else:
            colours = dict(fg=ERROR, bg="#3a0f14", edge="#a04646")
            tip = "Board not connected. Click to connect or flash firmware."
        self.setStyleSheet(self.STYLE.format(**colours))
        self.setToolTip(tip)
