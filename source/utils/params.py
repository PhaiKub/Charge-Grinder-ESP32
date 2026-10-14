import threading

LIMBUS_NAME = "LimbusCompany"

SELECTED = ["YISANG", "DONQUIXOTE" , "ISHMAEL", "RODION", "SINCLAIR", "GREGOR"]
GIFTS = []
TEAM = ["BURN"]
NAME_ORDER = 0
DUPLICATES = False

LOG = True
BONUS = False
COLLECT = True
RESTART = True
ALTF4 = False
ALTF4_lux = False
NETZACH = False
SKIP = True
WINRATE = False
WISHMAKING = False
BUFF = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
CARD = [1, 0, 2, 3, 4]
KEYWORDLESS = {}
HARD = False
EXTREME = False
APP = None

HOS_MODE = False

PICK = {}
IGNORE = {}
PICK_ALL = {}

WARNING = None
WINDOW = (0, 0, 1920, 1080)
SCREEN = None

pause_event = threading.Event()
stop_event = threading.Event()
STOP_REASON = None

LVL = 1
SUPER = "shop" # for Hard MD
DEAD = 0
IDX = 0
TO_UPTIE = {}
MOVE_ANIMATION = False

# Macro behavior configuration.
MACRO_PROFILE = "SAFE"
MACRO_RHYTHM = True
KEY_ERRORS = 0
