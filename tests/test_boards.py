import json
from types import SimpleNamespace

from cg_esp32 import boards


def test_every_board_has_a_unique_id_and_known_chip():
    ids = [b.id for b in boards.BOARDS]
    assert len(ids) == len(set(ids))
    assert {b.chip for b in boards.BOARDS} <= {"esp32s3", "esp32s2"}


def test_board_for_firmware_keeps_preferred_board_on_same_image():
    single = boards.BOARDS_BY_ID["esp32s3-single"]
    assert boards.board_for_firmware("esp32s3", single) is single
    assert boards.board_for_firmware("esp32s3-debug", None).firmware == "esp32s3"
    assert boards.board_for_firmware("lolin_s2_mini", single).chip == "esp32s2"
    assert boards.board_for_firmware(None) is None
    assert boards.board_for_firmware("rp2040") is None


def test_find_image_reads_version(tmp_path):
    board = boards.BOARDS_BY_ID["esp32s3-devkitc"]
    assert boards.find_image(board, tmp_path) is None
    (tmp_path / "esp32s3.bin").write_bytes(b"\xe9")
    assert boards.find_image(board, tmp_path).version == "unknown"
    (tmp_path / "esp32s3.json").write_text(json.dumps({"version": "0.2.0", "chip": "esp32s3"}))
    image = boards.find_image(board, tmp_path)
    assert (image.version, image.chip) == ("0.2.0", "esp32s3")


def test_version_compare():
    assert boards.is_newer("0.2.0", "0.1.0")
    assert boards.is_newer("0.10.0", "0.9.9")
    assert not boards.is_newer("0.1.0", "0.1.0")
    assert not boards.is_newer("unknown", "0.1.0")
    assert boards.is_newer("0.2.0", "dev")


def test_list_ports_orders_native_then_uart(monkeypatch):
    fake = [
        SimpleNamespace(device="COM12", vid=None, product=None, description="Bluetooth link (COM12)"),
        SimpleNamespace(device="COM6", vid=0x1A86, product=None, description="USB-SERIAL CH340 (COM6)"),
        SimpleNamespace(device="COM5", vid=0x303A, product=None, description="USB Serial Device (COM5)"),
    ]
    monkeypatch.setattr(boards.serial.tools.list_ports, "comports", lambda: fake)
    ports = boards.list_ports()
    assert [(p.device, p.kind) for p in ports] == [("COM5", "native"), ("COM6", "uart"), ("COM12", "other")]
    assert ports[1].label == "COM6  (CH340)"
    assert ports[2].description == "Bluetooth link"
