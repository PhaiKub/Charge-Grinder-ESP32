"""HID keyboard usage ids (USB HID Usage Tables, page 0x07).

The firmware sends these raw, so this is the only key table in the project.
"""

KEY_CODES = {
    **{chr(ord("a") + i): 0x04 + i for i in range(26)},
    **{str(n): 0x1E + (n - 1) for n in range(1, 10)},
    "0": 0x27,
    "enter": 0x28, "return": 0x28,
    "esc": 0x29, "escape": 0x29,
    "backspace": 0x2A,
    "tab": 0x2B,
    "space": 0x2C,
    "minus": 0x2D,
    "equal": 0x2E,
    "[": 0x2F,
    "]": 0x30,
    "\\": 0x31,
    ";": 0x33,
    "quote": 0x34,
    "`": 0x35,
    ",": 0x36,
    ".": 0x37,
    "/": 0x38,
    **{f"f{n}": 0x3A + (n - 1) for n in range(1, 13)},
    "insert": 0x49,
    "home": 0x4A,
    "pageup": 0x4B, "pgup": 0x4B,
    "delete": 0x4C, "del": 0x4C,
    "end": 0x4D,
    "pagedown": 0x4E, "pgdn": 0x4E,
    "right": 0x4F,
    "left": 0x50,
    "down": 0x51,
    "up": 0x52,
    "numpad_0": 0x62,
    **{f"numpad_{n}": 0x59 + (n - 1) for n in range(1, 10)},
    "ctrl": 0xE0, "lctrl": 0xE0,
    "shift": 0xE1, "lshift": 0xE1,
    "alt": 0xE2, "lalt": 0xE2,
    "win": 0xE3, "lwin": 0xE3,
    "rctrl": 0xE4,
    "rshift": 0xE5,
    "ralt": 0xE6,
    "rwin": 0xE7,
}

MOUSE_BUTTONS = {"left": 1, "right": 2, "middle": 4}


def key_code(key: str) -> int:
    try:
        return KEY_CODES[key.lower()]
    except KeyError:
        raise ValueError(f"unknown key: {key!r}") from None


def button_mask(button: str) -> int:
    try:
        return MOUSE_BUTTONS[button.lower()]
    except KeyError:
        raise ValueError(f"unknown mouse button: {button!r}") from None
