import platform

from PySide6.QtWidgets import QMessageBox


def check_device(app_parent=None):
    """Connect to the ESP32-S3 before the window opens; explain what to do if it isn't there."""
    if platform.system() != "Windows":
        QMessageBox.critical(app_parent, "Windows Only", "Charge-Grinder-ESP32 runs on Windows only.")
        return False

    from source.utils.os_esp32_backend import connect

    while True:
        try:
            version = connect()
            print(f"ESP32-S3 connected, firmware {version}")
            return True
        except Exception as exc:
            msg = QMessageBox(app_parent)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("ESP32-S3 Not Connected")
            msg.setText("Could not talk to the ESP32-S3.")
            msg.setInformativeText(
                f"{exc}\n\n"
                "Plug the board's native USB (OTG) port into this PC and make sure "
                "the Charge-Grinder-ESP32 firmware is flashed, then press Retry."
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close)
            if msg.exec() != QMessageBox.StandardButton.Retry:
                return False
