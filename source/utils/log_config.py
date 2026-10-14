import logging, sys, os

from source.utils.discord_webhook import create_handler_from_env


_EXCEPTHOOK_INSTALLED = False
_ORIGINAL_EXCEPTHOOK = None

def _is_onefile_temp_path(path: str) -> bool:
    normalized = os.path.normcase(os.path.abspath(path))
    return "\\appdata\\local\\temp\\onefil" in normalized


def _launched_executable_dir():
    argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
    exe = os.path.abspath(sys.executable)

    if argv0 and os.path.isfile(argv0) and not _is_onefile_temp_path(argv0):
        return os.path.dirname(argv0)

    if exe and os.path.isfile(exe) and not _is_onefile_temp_path(exe):
        return os.path.dirname(exe)

    if argv0:
        return os.path.dirname(argv0)

    return os.path.dirname(exe)


def _runtime_base_path():
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        return os.path.dirname(appimage_path)

    # Nuitka sets __compiled__; PyInstaller exposes sys.frozen.
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        return _launched_executable_dir()

    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def _attach_webhook_handler():
    handler, error_message = create_handler_from_env()
    if error_message:
        logging.warning(error_message)
        return False

    if handler:
        logging.getLogger().addHandler(handler)
        logging.info("Discord webhook notifications enabled.")
        return True

    return False


def _install_excepthook():
    global _EXCEPTHOOK_INSTALLED, _ORIGINAL_EXCEPTHOOK
    if _EXCEPTHOOK_INSTALLED:
        return

    _ORIGINAL_EXCEPTHOOK = sys.excepthook

    def log_uncaught_exceptions(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        _ORIGINAL_EXCEPTHOOK(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_uncaught_exceptions
    _EXCEPTHOOK_INSTALLED = True

def setup_logging(enable_logging: bool = True, log_file: str = "game.log", log_level=logging.INFO):
    if enable_logging:
        base_path = _runtime_base_path()
        log_path = os.path.join(base_path, log_file)
        print(f"Logging enabled. Log file: {log_path}")

        logging.basicConfig(
            filename=str(log_path),
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            force=True
        )
    else:
        logging.basicConfig(
            level=log_level,
            handlers=[logging.NullHandler()],
            force=True
        )

    _attach_webhook_handler()

    _install_excepthook()
