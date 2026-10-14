from source_app.utils import *
from source_app.cache import CacheWorker
from source.utils.paths import APP_VERSION

from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class VersionChecker(QObject):
    updateAvailable = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.manager.finished.connect(self._on_finished)

    def check(self):
        req = QNetworkRequest(QUrl("https://api.github.com/repos/Walpth/Charge-Grinder/releases/latest"))
        req.setRawHeader(b"User-Agent", b"MirrorDungeonBot-VersionChecker/1.0")
        req.setRawHeader(b"Accept", b"application/vnd.github.v3+json")
        req.setTransferTimeout(10000)
        self.manager.get(req)

    def _on_finished(self, reply):
        reply.deleteLater()

        if reply.error() != QNetworkReply.NetworkError.NoError:
            status_code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            err_str = reply.errorString()
            print("Network error:", err_str, "status:", status_code)
            self.updateAvailable.emit(True)
            return

        data = bytes(reply.readAll()).decode('utf-8')
        try:
            j = json.loads(data)
            tag = j.get("tag_name", "").lstrip("vV")
            is_up_to_date = self._compare_versions(tag, APP_VERSION)
        except Exception as e:
            print("Parse error:", e)
            is_up_to_date = True
        self.updateAvailable.emit(is_up_to_date)

    def _compare_versions(self, latest, current):
        try:
            a = [int(x) for x in latest.split(".") if x.isdigit()]
            b = [int(x) for x in current.split(".") if x.isdigit()]
            n = max(len(a), len(b))
            a += [0] * (n - len(a)); b += [0] * (n - len(b))
            return a <= b
        except Exception:
            return True

# Handle bot proccess
class BotWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    warning = pyqtSignal(str)

    def __init__(self, count, count_exp, count_thd, teams, settings, hard, app):
        super().__init__()
        self.count = count
        self.count_exp = count_exp
        self.count_thd = count_thd
        self.teams = teams
        self.settings = settings
        self.hard = hard
        self.app = app

        self.cache_thread = None
        self.cache_worker = None

    def run(self):
        try:
            teams_filtered = {k: v for k, v in self.teams.items() if k < 7}
            if teams_filtered:
                self.start_cache_thread(teams_filtered, self.settings, self.hard)

            Bot.execute_me(
                self.count,
                self.count_exp,
                self.count_thd,
                self.teams,
                self.settings,
                self.hard,
                self.app,
                warning=self.warning.emit
            )
        except Exception as e:
            logging.exception("Uncaught exception in BotWorker thread")  
            self.error.emit(str(e))
        finally:
            self.stop_cache_thread()
            self.finished.emit()

    def start_cache_thread(self, teams, settings, hard):
        self.cache_thread = QThread()
        self.cache_worker = CacheWorker(teams, settings, hard)

        self.cache_worker.moveToThread(self.cache_thread)
        self.cache_thread.started.connect(self.cache_worker.run)
        self.cache_worker.finished.connect(self.cache_thread.quit)
        self.cache_worker.finished.connect(self.cache_worker.deleteLater)
        self.cache_thread.finished.connect(self.cache_thread.deleteLater)

        self.cache_thread.start()

    def stop_cache_thread(self):
        if not self.cache_thread:
            return

        if self.cache_thread.isRunning():
            self.cache_thread.quit()
            self.cache_thread.wait(3000)

        self.cache_thread = None
        self.cache_worker = None