import sys, os, json, hashlib, copy
from datetime import datetime, timezone, timedelta

from source_app.run_bridge import BRIDGE_ERROR_MESSAGE, RAISE_ERROR
import source.utils.params as p
from source.utils.log_config import *
import Bot

from stats import log_to_csv

# os.environ['QT_LOGGING_RULES'] = 'qt.qpa.*=false'

from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLineEdit, QLabel, QGraphicsOpacityEffect, QMessageBox, QLayout, QHBoxLayout, QVBoxLayout, QScrollArea, QComboBox, QMainWindow, QFrame, QStyleFactory
from PySide6.QtGui import QIcon, QFont, QPixmap, QPainter, QIntValidator, QFontDatabase, QRegularExpressionValidator
from PySide6.QtCore import Qt, QTimer, QEvent, QPropertyAnimation, QObject, Signal as pyqtSignal, QThread, QSize, QRect, QPoint, QRegularExpression, Slot as pyqtSlot

import webbrowser
from urllib.request import urlopen
