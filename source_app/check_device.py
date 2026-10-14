import platform

from PySide6.QtWidgets import QMessageBox


def check_device(app_parent=None):
    """The board only works on Windows. The board itself is found by the
    device page inside the main window (device_panel.py), not here."""
    if platform.system() != "Windows":
        QMessageBox.critical(app_parent, "Windows Only", "Charge-Grinder-ESP32 runs on Windows only.")
        return False
    return True
