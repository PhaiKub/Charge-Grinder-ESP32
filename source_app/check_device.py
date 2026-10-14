import platform

from PySide6.QtWidgets import QDialog, QMessageBox


def check_device(app_parent=None):
    """Find the board before the main window opens.

    Shows the device window, which scans for the board and closes by itself
    once one answers; from there the user can also pick a port or flash the
    firmware. Returns False if the user quits without a board.
    """
    if platform.system() != "Windows":
        QMessageBox.critical(app_parent, "Windows Only", "Charge-Grinder-ESP32 runs on Windows only.")
        return False

    from source_app.device_dialog import DeviceDialog

    # No parent: the main window isn't shown yet, and an owned dialog gets no taskbar button.
    return DeviceDialog(None, startup=True).exec() == QDialog.DialogCode.Accepted
