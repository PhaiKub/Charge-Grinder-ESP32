"""PlatformIO post-build step: write dist/<env>.bin and dist/<env>.json.

The .bin merges bootloader, partition table, boot_app0 and the app into one
image that is flashed at offset 0x0, so the app (host/cg_esp32/flasher.py)
needs only esptool and this one file, not PlatformIO.
"""

import json
import os

Import("env")  # noqa: F821  (provided by PlatformIO/SCons)


def merge_bin(source, target, env):
    if env.GetProjectOption("custom_dist", "yes") != "yes":
        return
    board = env.BoardConfig()
    name = env.subst("$PIOENV")
    dist = os.path.join(env.subst("$PROJECT_DIR"), "dist")
    os.makedirs(dist, exist_ok=True)
    out = os.path.join(dist, name + ".bin")

    images = [f'{offset} "{env.subst(image)}"' for offset, image in env.get("FLASH_EXTRA_IMAGES", [])]
    images.append(f'$ESP32_APP_OFFSET "{target[0].get_abspath()}"')
    cmd = " ".join([
        '"$PYTHONEXE" "$OBJCOPY"',
        "--chip", board.get("build.mcu"),
        "merge_bin", "-o", f'"{out}"',
        "--flash_mode", "${__get_board_flash_mode(__env__)}",
        "--flash_freq", "${__get_board_f_image(__env__)}",
        "--flash_size", board.get("upload.flash_size", "4MB"),
        *images,
    ])
    env.Execute(env.VerboseAction(cmd, f"Merging firmware image {out}"))

    info = {
        "board": name,
        "chip": board.get("build.mcu"),
        "version": env.GetProjectConfig().get("fw", "version"),
        "file": name + ".bin",
    }
    with open(os.path.join(dist, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
        fh.write("\n")


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", merge_bin)  # noqa: F821
