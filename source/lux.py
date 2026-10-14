from source.utils.utils import *
from source.battle import fight

def is_full(shift):
    image = screenshot(region=(530 - shift, 1003, 5, 5))
    y, x = image.shape[0] // 2, image.shape[1] // 2
    b, g, r = image[y, x]
    return (
        0 <= r <= 10 and
        160 <= g <= 255 and
        50 <= b <= 140
    )

def check_enkephalin(shift=0): # 227
    if not is_full(shift=shift): return

    ClickAction((601 - shift, 1004), ver="ConfirmInvert.1").execute(click)
    win_click(1208, 496)
    Action("ConfirmInvert.1", ver="connecting").execute(click)
    connection()
    time.sleep(0.5)
    gui.press("esc")
    time.sleep(0.5)

def select_thd_level():
    choices = LocateRGB.locate_all(PTH["EnterSmall"], region=REG["thd!"])
    if not choices:
        return

    while True:
        choices.sort(key=lambda box: box[1], reverse=True)
        x, y = gui.center(choices[0])
        if y < 620:
            # Lower options are locked
            break

        img = screenshot(region=(1340, 783, 3, 3))
        _, _, v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[0][0]
        if v > 127:
            # We can't scroll further down
            break
        
        win_moveTo(950, 540)
        win_dragTo(950, 220)
        choices = LocateRGB.locate_all(PTH["EnterSmall"], region=REG["thd!"])
        if not choices:
            return

    win_click(x, y)
    time.sleep(0.5)

def start_lux():
    try:
        if now.button("Drive"):
            Action("Drive", ver="Lux").execute(click)
        if now.button("Lux"):
            Action("Lux", ver="Exp").execute(click)
    except RuntimeError:
        print("Lux init failed")


def team_setup(teams, index):
    lux_list = ["SLASH", "PIERCE", "BLUNT", "WRATH", "LUST", "SLOTH", "GLUTTONY", "GLOOM", "PRIDE", "ENVY"]
    team_idx = [i for i in teams.keys() if i >= 7]
    if index < len(team_idx):
        p.TEAM = [lux_list[team_idx[index] - 7]]
        p.SELECTED = [list(SINNERS.keys())[i] for i in list(teams[team_idx[index]]["sinners"])]


def grind_lux(count_exp, count_thd, teams):
    team_setup(teams, index=0)
    if count_exp or count_thd:
        logging.info("Luxcavation started")

    while count_exp:
        try:
            if not now.button("winrate") and not now.button("Exp"): start_lux()
            if p.LIMBUS_NAME not in (win := gui.getActiveWindowTitle()): pause(win)
            time.sleep(0.5)

            choices = LocateRGB.locate_all(PTH["EnterDoor"], region=REG["pick!"])
            if len(choices) != 0:
                if p.NETZACH: check_enkephalin(shift=227)

                choices.sort(key=lambda box: box[0], reverse=True)
                print(choices)
                win_click(gui.center(choices[0]))
                time.sleep(0.5)

            fight(lux=True)

            if now.button("victory"):
                time.sleep(0.5)
                gui.press("esc")
                if loc.button("Exp"):
                    count_exp -= 1
                    logging.info("Exp Luxcavation")
            elif now.button("defeat"):
                time.sleep(0.5)
                if not p.RESTART:
                    raise RuntimeError("Luxcavation failed!")
                gui.press("enter")
        except gui.PauseException as e:
            pause(e.window)

    team_setup(teams, index=1)
    while count_thd:
        try:
            if not now.button("winrate") and not now.button("Exp"): start_lux()
            if p.LIMBUS_NAME not in (win := gui.getActiveWindowTitle()): pause(win)

            if now.button("Exp") and not now.button("EnterSmall", "thd!"):
                if p.NETZACH: check_enkephalin(shift=227)

                win_click(225, 492)
                time.sleep(1)
                win_click(553, 721)

                wait_while_condition(lambda: not now.button("EnterSmall", "thd!"))
                time.sleep(0.5)

            select_thd_level()
            fight(lux=True)

            if now.button("victory"):
                time.sleep(0.5)
                gui.press("esc")
                if loc.button("Exp"):
                    count_thd -= 1
                    logging.info("Thread Luxcavation")
            elif now.button("defeat"):
                time.sleep(0.5)
                if not p.RESTART:
                    raise RuntimeError("Luxcavation failed!")
                gui.press("enter")
        except gui.PauseException as e:
            pause(e.window)

    wait_while_condition(lambda: not now.button("Exp"))
    time.sleep(1)
    gui.press("esc")
    if p.COLLECT: collect_dailies()
    logging.info("Done with Luxcavation!")


def collect_dailies():
    Action("Window", ver="Settings").execute(click)
    ClickAction((1621, 352), ver="PassMissions").execute(click)
    Action("PassMissions", ver="Daily").execute(click)
    wait_while_condition( 
        lambda: 0 < len(LocateRGB.locate_all(PTH["collect"], region=REG["collect"], threshold=50)),
        click_collect
    )
    gui.press("esc")

def click_collect():
    now_click.button("collect")
    connection()
    time.sleep(1)
