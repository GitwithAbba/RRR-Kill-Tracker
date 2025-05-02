import os
import json
import psutil
import requests
import threading
import webbrowser
import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext
from tkinter import messagebox
import sys
from packaging import version
import time
import datetime
from PIL import Image, ImageTk
from datetime import datetime, timedelta
import json
import winsound

from config import BACKEND_URL, API_KEY, VALIDATE_URL, REPORT_KILL_URL, REPORT_DEATH_URL


# ─── Version & globals ──────────────────────────────────────────────────────────
local_version = "7.0"
api_key = {"value": None}

global_game_mode = "Nothing"
global_active_ship = "N/A"
global_active_ship_id = "N/A"
global_player_geid = "N/A"
global_active_zone = "Unknown"

global_ship_list = [
    "DRAK",
    "ORIG",
    "AEGS",
    "ANVL",
    "CRUS",
    "BANU",
    "MISC",
    "KRIG",
    "XNAA",
    "ARGO",
    "VNCL",
    "ESPR",
    "RSI",
    "CNOU",
    "GRIN",
    "TMBL",
    "GAMA",
]


# ─── Helpers ────────────────────────────────────────────────────────────────────
def resource_path(rel):
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(".")
    return os.path.join(base, rel)


def check_for_updates():
    url = "https://api.github.com/repos/martinmedic/BeowulfHunterPy/releases/latest"
    try:
        r = requests.get(url, headers={"User-Agent": "Killtracker/1.1"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            remote = data.get("tag_name", "v0").lstrip("v")
            link = data.get("html_url", "")
            if version.parse(local_version) < version.parse(remote):
                return f"Update available: {remote}. Download here: {link}"
    except Exception:
        pass
    return None


class EventLogger:
    def __init__(self, widget):
        self.w = widget

    def log(self, m):
        self.w.config(state=tk.NORMAL)
        self.w.insert(tk.END, m + "\n")
        self.w.config(state=tk.DISABLED)
        self.w.see(tk.END)


def show_loading_animation(logger, app):
    for dots in [".", "..", "..."]:
        logger.log(dots)
        app.update_idletasks()
        time.sleep(0.2)


def destroy_player_zone(line, logger):
    global global_active_ship
    global global_active_ship_id
    if ("N/A" != global_active_ship) or ("N/A" != global_active_ship_id):
        print(f"Ship Destroyed: {global_active_ship} with ID: {global_active_ship_id}")
        global_active_ship = "N/A"
        global_active_ship_id = "N/A"


def set_ac_ship(line, logger):
    global global_active_ship
    global_active_ship = line.split(" ")[5][1:-1]
    print("Player has entered ship: ", global_active_ship)


# ─── Zone & ship parsing ────────────────────────────────────────────────────────
def set_player_zone(line: str, logger: EventLogger):
    global global_active_zone, global_active_ship, global_active_ship_id

    # 1) pull out the *real* map‐zone
    try:
        # log lines look like "...OnEntityEnterZone -> Zone ['OOC_Stanton_1b_Aberdeen']..."
        zone_str = line.split("-> Zone ")[1].split(" ")[0].strip("[]\"'")
        global_active_zone = zone_str
        logger.log(f"🌐 Entered Zone: {global_active_zone}")
    except Exception:
        # if that fails, leave global_active_zone unchanged
        pass

    # 2) *then* fall back to your existing ship‐entity logic:
    line_index = line.index("-> Entity ") + len("-> Entity ")
    if line_index == len("-> Entity "):
        # malformed, clear out
        global_active_ship = "N/A"
        global_active_ship_id = "N/A"
        return

    potential_zone = line[line_index:].split(" ")[0][1:-1]
    for x in global_ship_list:
        if potential_zone.startswith(x):
            global_active_ship = potential_zone[: potential_zone.rindex("_")]
            global_active_ship_id = potential_zone[potential_zone.rindex("_") + 1 :]
            logger.log(f"🚀 Active Ship: {global_active_ship}")
            return


def check_if_process_running(process_name):
    """Check if a process is running by name."""
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        if process_name.lower() in proc.info["name"].lower():
            return proc.info["exe"]
    return None


def find_game_log_in_directory(directory):
    """Search for Game.log in the directory and its parent directory."""
    game_log_path = os.path.join(directory, "Game.log")
    if os.path.exists(game_log_path):
        print(f"Found Game.log in: {directory}")
        return game_log_path
    # If not found in the same directory, check the parent directory
    parent_directory = os.path.dirname(directory)
    game_log_path = os.path.join(parent_directory, "Game.log")
    if os.path.exists(game_log_path):
        print(f"Found Game.log in parent directory: {parent_directory}")
        return game_log_path
    return None


def set_sc_log_location():
    """Check for RSI Launcher and Star Citizen Launcher, and set SC_LOG_LOCATION accordingly."""
    # Check if RSI Launcher is running
    rsi_launcher_path = check_if_process_running("RSI Launcher")
    if not rsi_launcher_path:
        print("RSI Launcher not running.")
        return None

    print("RSI Launcher running at:", rsi_launcher_path)

    # Check if Star Citizen Launcher is running
    sc_launcher_path = check_if_process_running("StarCitizen")
    if not sc_launcher_path:
        print("Star Citizen Launcher not running.")
        return None

    print("Star Citizen Launcher running at:", sc_launcher_path)

    # Search for Game.log in the folder next to StarCitizen_Launcher.exe
    star_citizen_dir = os.path.dirname(sc_launcher_path)
    print(f"Searching for Game.log in directory: {star_citizen_dir}")
    log_path = find_game_log_in_directory(star_citizen_dir)

    if log_path:
        print("Setting SC_LOG_LOCATION to:", log_path)
        os.environ["SC_LOG_LOCATION"] = log_path
        return log_path
    else:
        print("Game.log not found in expected locations.")
        return None


# Substrings to ignore
ignore_kill_substrings = [
    "PU_Pilots",
    "NPC_Archetypes",
    "PU_Human",
    "kopion",
    "marok",
]


def check_substring_list(line, substring_list):
    """
    Check if any substring from the list is present in the given line.
    """
    for substring in substring_list:
        if substring.lower() in line.lower():
            return True
    return False


def check_exclusion_scenarios(line, logger):
    global global_game_mode
    if global_game_mode == "EA_FreeFlight" and -1 != line.find("Crash"):
        print("Probably a ship reset, ignoring kill!")
        return False
    return True


# ─── Key validation ─────────────────────────────────────────────────────────────
def validate_api_key(key: str) -> bool:
    """
    Hit GET /keys/validate with Bearer <key>.
    """
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(VALIDATE_URL, headers=headers, timeout=5)
        return r.status_code in (200, 201)
    except Exception as e:
        print("Key validation error:", e)
        return False


def save_api_key(key: str):
    # compute a 72‑hour expiration from now
    expires_at = (datetime.utcnow() + timedelta(hours=72)).isoformat() + "Z"
    payload = {"key": key, "expires_at": expires_at}

    # write both the key and its expiration to disk
    with open("killtracker_key.cfg", "w") as f:
        json.dump(payload, f)

    # store in memory for immediate use
    api_key["value"] = key


# Activate the API key by sending it to the server
def activate_key(key_entry):
    entered_key = key_entry.get().strip()  # Access key_entry here
    if entered_key:
        log_file_location = set_sc_log_location()  # Assuming this is defined elsewhere
        if log_file_location:
            player_name = get_player_name(log_file_location)  # Retrieve the player name
            if player_name:
                if validate_api_key(entered_key):
                    # Pass both the key and player name
                    save_api_key(entered_key)  # Save the key for future use
                    logger.log(
                        "Key activated and saved. Servitor connection established."
                    )
                else:
                    logger.log(
                        "Invalid key or player name. Please enter a valid API key."
                    )
            else:
                logger.log(
                    "RSI Handle not found. Please ensure the game is running and the log file is accessible."
                )
        else:
            logger.log("Log file location not found.")
    else:
        logger.log("No key entered. Please input a valid key.")


def get_player_name(log_file_location):
    # Retrieve the RSI handle using the existing function
    rsi_handle = find_rsi_handle(log_file_location)
    find_rsi_geid(log_file_location)
    if not rsi_handle:
        print("Error: RSI handle not found.")
        return None
    return rsi_handle


# ─── Play sound on kill ──────────────────────────────────────────────────────
def play_kill_sound():
    path = resource_path(os.path.join("assets", "kill.wav"))
    winsound.PlaySound(path, winsound.SND_FILENAME)


# ─── Kill parsing & upload ──────────────────────────────────────────────────────
def parse_kill_line(line: str, target: str, logger: EventLogger):
    if global_game_mode == "EA_FreeFlight" and "Crash" in line:
        return

    parts = line.split(" ")
    kill_time = parts[0].strip("<>")
    killed = parts[5].strip("'")
    killed_zone = parts[9].strip("'")
    killer = parts[12].strip("'")
    weapon = parts[15].strip("'")
    dmg = parts[21].strip("'")
    victim_ship = None
    if "_" in killed_zone:
        # e.g. "DRAK_Corsair_30853" → "DRAK_Corsair"
        victim_ship = killed_zone.rsplit("_", 1)[0]

    mode = "ac-kill" if global_game_mode.startswith("EA_") else "pu-kill"

    # — Death (you got killed) —
    if killed == target and killer.lower() != "unknown":
        death = {
            "killer": killer,
            "victim": target,
            "time": kill_time,
            "zone": global_active_zone,  # use the parsed zone
            "weapon": weapon,
            "damage_type": dmg,
            "rsi_profile": f"https://robertsspaceindustries.com/citizens/{killer}",
            "game_mode": global_game_mode,
            "mode": mode,
            "killers_ship": global_active_ship,  # your ship at time of death
            "victim_ship": global_active_ship,  # same, since *you* are the victim
        }

        # ← INSERT DEBUG LOG HERE:
        logger.log(f"→ POST payload: {death}")

        headers = {
            "Authorization": f"Bearer {api_key['value']}",
            "Content-Type": "application/json",
        }
        try:
            requests.post(
                f"{BACKEND_URL}/reportDeath", headers=headers, json=death, timeout=5
            )
        except Exception as e:
            logger.log(f"❌ Failed to report death: {e}")
        logger.log("You DIED.")
        return

    # — Kill (you killed someone else) —
    json_data = {
        "player": target,
        "victim": killed,
        "time": kill_time,
        "zone": global_active_zone,  # your real map‐zone
        "weapon": weapon,
        "rsi_profile": f"https://robertsspaceindustries.com/citizens/{killed}",
        "game_mode": global_game_mode,
        "mode": mode,
        "client_ver": local_version,
        "killers_ship": global_active_ship,  # your ship at time of kill
        "victim_ship": victim_ship,  # theirs
        "damage_type": dmg,
    }

    # ← INSERT DEBUG LOG HERE:
    logger.log(f"→ POST payload: {json_data}")

    headers = {
        "Authorization": f"Bearer {api_key['value']}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(REPORT_KILL_URL, headers=headers, json=json_data, timeout=5)
        if r.status_code in (200, 201):
            play_kill_sound()
            logger.log(f"✅ Kill recorded: {killed} @ {kill_time}")
        else:
            logger.log(f"❌ Upload failed ({r.status_code})")
    except Exception as e:
        logger.log(f"Error sending kill: {e}")


def read_existing_log(log_file_location, rsi_name):
    sc_log = open(log_file_location, "r")
    lines = sc_log.readlines()
    for line in lines:
        read_log_line(line, rsi_name, True, logger)


def find_rsi_handle(log_file_location):
    acct_str = "<Legacy login response> [CIG-net] User Login Success"
    sc_log = open(log_file_location, "r")
    lines = sc_log.readlines()
    for line in lines:
        if -1 != line.find(acct_str):
            line_index = line.index("Handle[") + len("Handle[")
            if 0 == line_index:
                print("RSI_HANDLE: Not Found!")
                exit()
            potential_handle = line[line_index:].split(" ")[0]
            return potential_handle[0:-1]
    return None


def find_rsi_geid(log_file_location):
    global global_player_geid
    acct_kw = "AccountLoginCharacterStatus_Character"
    sc_log = open(log_file_location, "r")
    lines = sc_log.readlines()
    for line in lines:
        if -1 != line.find(acct_kw):
            global_player_geid = line.split(" ")[11]
            print("Player geid: " + global_player_geid)
            return


def set_game_mode(line, logger):
    global global_game_mode
    global global_active_ship
    global global_active_ship_id
    split_line = line.split(" ")
    game_mode = split_line[8].split("=")[1].strip('"')
    if game_mode != global_game_mode:
        global_game_mode = game_mode

    if "SC_Default" == global_game_mode:
        global_active_ship = "N/A"
        global_active_ship_id = "N/A"


def setup_gui(game_running):
    app = tk.Tk()
    app.title("RRRthur Tracker")
    app.geometry("650x450")
    app.resizable(False, False)
    app.configure(bg="#1a1a1a")

    try:
        font_path = resource_path("Orbitron.ttf")
        custom_font = tkFont.Font(file=font_path, size=12)
        app.option_add("*Font", custom_font)
    except Exception as e:
        print(f"Failed to load custom font: {e}")

    # Set the icon
    try:
        icon_path = resource_path("3R_Transparent.ico")
        print("Resolved icon path:", icon_path)
        if os.path.exists(icon_path):
            app.iconbitmap(icon_path)
            print(f"Icon loaded successfully from: {icon_path}")
        else:
            print(f"Icon not found at: {icon_path}")
    except Exception as e:
        print(f"Error setting icon: {e}")

    # Add Banner
    try:
        banner_path = resource_path(os.path.join("assets", "3R_Transparent.png"))
        original_image = Image.open(banner_path)

        # Resize to 50% of original size (or change to specific size like (600, 150))
        resized_image = original_image.resize((179, 146), Image.Resampling.LANCZOS)

        banner_image = ImageTk.PhotoImage(resized_image)
        banner_label = tk.Label(app, image=banner_image, bg="#1a1a1a")
        banner_label.image = banner_image
        banner_label.pack(pady=(0, 10))
    except Exception as e:
        print(f"Error loading banner image: {e}")

    # Check for Updates
    update_message = check_for_updates()
    if update_message:
        update_label = tk.Label(
            app,
            text=update_message,
            font=("Times New Roman", 12),
            fg="#ff5555",
            bg="#1a1a1a",
            wraplength=700,
            justify="center",
            cursor="hand2",
        )
        update_label.pack(pady=(10, 10))

        def open_github(event):
            try:
                url = update_message.split("Download it here: ")[-1]
                webbrowser.open(url)
            except Exception as e:
                print(f"Error opening GitHub link: {e}")

        update_label.bind("<Button-1>", open_github)

    if game_running:
        # API Key Input
        key_frame = tk.Frame(app, bg="#1a1a1a")
        key_frame.pack(pady=(10, 10))

        key_label = tk.Label(
            key_frame,
            text="Enter Key:",
            font=("Times New Roman", 12),
            fg="#ffffff",
            bg="#1a1a1a",
        )
        key_label.pack(side=tk.LEFT, padx=(0, 5))

        # key_entry = tk.Entry(key_frame, width=30, font=("Times New Roman", 12))
        key_entry = tk.Entry(
            key_frame,
            width=30,
            font=("Orbitron", 12),
            highlightthickness=2,
            highlightbackground="#ff0000",
            highlightcolor="#ff0000",
            bg="#0a0a0a",
            fg="#ffffff",
            insertbackground="#ff5555",
        )
        key_entry.pack(side=tk.LEFT)

        # API Status Label
        api_status_label = tk.Label(
            app,
            text="API Status: Not Validated",
            font=("Times New Roman", 12),
            fg="#ffffff",
            bg="#1a1a1a",
        )
        api_status_label.pack(pady=(10, 10))

        # Activate API Key
        def activate_key():
            entered_key = key_entry.get().strip()
            if not entered_key:
                logger.log("No key entered. Please input a valid key.")
                api_status_label.config(text="API Status: Invalid", fg="red")
                return

            log_file_location = set_sc_log_location()
            if not log_file_location:
                logger.log("Log file location not found.")
                api_status_label.config(text="API Status: Error", fg="yellow")
                return

            player_name = get_player_name(log_file_location)
            if not player_name:
                logger.log(
                    "RSI Handle not found. Please ensure the game is running and the log file is accessible."
                )
                api_status_label.config(text="API Status: Error", fg="yellow")
                return

            # Now validate
            if validate_api_key(entered_key):
                # success path
                save_api_key(entered_key)
                logger.log("Key activated and saved. Servitor connection established.")
                api_status_label.config(text="API Status: Valid", fg="green")

                # start a 72h countdown
                expires_at = datetime.utcnow() + timedelta(hours=72)
                start_api_key_countdown(expires_at, api_status_label)
            else:
                # failure path
                logger.log("Invalid key. Please enter a valid API key.")
                api_status_label.config(text="API Status: Invalid", fg="red")

        button_style = {
            "bg": "#0f0f0f",
            "fg": "#ff5555",
            "activebackground": "#330000",
            "activeforeground": "#ffffff",
            "relief": "ridge",
            "bd": 2,
            "font": ("Orbitron", 12),
        }

        activate_button = tk.Button(
            key_frame, text="Activate", command=activate_key, **button_style
        )
        activate_button.pack(side=tk.LEFT, padx=(5, 0))

        # Load Existing Key
        def load_existing_key():
            try:
                with open("killtracker_key.cfg", "r") as f:
                    info = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                logger.log("No existing key found. Please enter a valid key.")
                api_status_label.config(text="API Status: Invalid", fg="red")
                return

            entered_key = info.get("key")
            expires_at_str = info.get("expires_at")
            if not entered_key or not expires_at_str:
                logger.log("Invalid key file. Please enter a new key.")
                api_status_label.config(text="API Status: Invalid", fg="red")
                return

            if not validate_api_key(entered_key):
                logger.log("Invalid key. Please input a valid key.")
                api_status_label.config(text="API Status: Invalid", fg="red")
                return

            # success!
            api_key["value"] = entered_key
            logger.log(
                f"Existing key loaded: {entered_key}. Servitor connection established."
            )
            api_status_label.config(text="API Status: Valid", fg="green")

            expires_at = datetime.fromisoformat(info["expires_at"].rstrip("Z"))
            start_api_key_countdown(expires_at, api_status_label)

        button_style = {
            "bg": "#0f0f0f",
            "fg": "#ff5555",
            "activebackground": "#330000",
            "activeforeground": "#ffffff",
            "relief": "ridge",
            "bd": 2,
            "font": ("Orbitron", 12),
        }

        load_key_button = tk.Button(
            key_frame,
            text="Load Existing Key",
            command=load_existing_key,
            **button_style,
        )
        load_key_button.pack(side=tk.LEFT, padx=(5, 0))

        # Log Display
        text_area = scrolledtext.ScrolledText(
            app,
            wrap=tk.WORD,
            width=80,
            height=20,
            state=tk.DISABLED,
            bg="#121212",
            fg="#ff4444",
            insertbackground="#ff4444",
            highlightthickness=2,
            highlightbackground="#ff0000",
            highlightcolor="#ff0000",
            font=("Orbitron", 12),
        )
        text_area.pack(padx=10, pady=10)

        logger = EventLogger(text_area)

    else:
        # Relaunch Message
        message_label = tk.Label(
            app,
            text="You must launch Star Citizen before starting the tracker.\n\nPlease close this window, launch Star Citizen, and relaunch RRRthur Tracker. ",
            font=("Times New Roman", 14),
            fg="#ff4444",
            bg="#1a1a1a",
            wraplength=700,
            justify="center",
        )
        message_label.pack(pady=(50, 10))
        logger = None

    # Footer
    footer = tk.Frame(app, bg="#3e3b4d", height=50)
    footer.pack(side=tk.BOTTOM, fill=tk.X)

    footer_text = tk.Label(
        footer,
        text="RRRthur Tracker is a clone of BeowulfHunter which is a clone of BlightVeil's KillTracker - Credits: IronPoint: (DocHound), BlightVeil: (CyberBully-Actual, BossGamer09, Holiday)",
        font=("Times New Roman", 10),
        fg="#bcbcd8",
        bg="#3e3b4d",
        wraplength=600,
        justify="center",
    )
    footer_text.pack(padx=10, pady=5, fill="x")

    return app, logger


def start_api_key_countdown(expiration_time: datetime, api_status_label):
    """
    Show a live countdown to `expiration_time` on the given label.
    """

    def countdown():
        remaining = expiration_time - datetime.utcnow()
        if remaining.total_seconds() > 0:
            days = remaining.days
            hours, rem = divmod(remaining.seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            api_status_label.config(
                text=f"API Status: Valid (Expires in {days}d {hours}h {minutes}m {seconds}s)",
                fg="green",
            )
            api_status_label.after(1000, countdown)
        else:
            api_status_label.config(text="API Status: Expired", fg="red")

    countdown()


def read_log_line(line, rsi_name, upload_kills, logger):
    # 1) Game mode lines
    if "<Context Establisher Done>" in line:
        set_game_mode(line, logger)

    # 2) Always track when you ENTER a new map‐zone
    if "OnEntityEnterZone" in line:
        set_player_zone(line, logger)

    # 3) Always track when *you* get into a ship
    if (
        "CPlayerShipRespawnManager::OnVehicleSpawned" in line
        and global_game_mode != "SC_Default"
        and global_player_geid in line
    ):
        set_ac_ship(line, logger)

    # 4) If it’s a kill line for *you* (i.e. containing your handle), parse it
    if (
        rsi_name in line
        and "CActor::Kill" in line
        and not check_substring_list(line, ignore_kill_substrings)
        and upload_kills
    ):
        parse_kill_line(line, rsi_name, logger)

    # 5) If *you* died (vehicle destroyed / client dead) on your active ship
    if (
        "<Vehicle Destruction>" in line
        or "<local client>: Entering control state dead" in line
    ) and global_active_ship_id in line:
        destroy_player_zone(line, logger)


def tail_log(log_file_location, rsi_name, logger):
    """Read the log file and display events in the GUI."""
    global global_game_mode, global_player_geid
    sc_log = open(log_file_location, "r")
    if sc_log is None:
        logger.log(f"No log file found at {log_file_location}.")
        return

    logger.log("Kill Tracking Initiated...")
    logger.log("Enter key to establish Servitor connection...")

    # Read all lines to find out what game mode player is currently, in case they booted up late.
    # Don't upload kills, we don't want repeating last sessions kills incase they are actually available.
    lines = sc_log.readlines()
    print(
        "Loading old log (if available)! Kills shown will not be uploaded as they are stale."
    )
    for line in lines:
        read_log_line(line, rsi_name, False, logger)

    # Main loop to monitor the log
    last_log_file_size = os.stat(log_file_location).st_size
    while True:
        where = sc_log.tell()
        line = sc_log.readline()
        if not line:
            time.sleep(1)
            sc_log.seek(where)
            if last_log_file_size > os.stat(log_file_location).st_size:
                sc_log.close()
                sc_log = open(log_file_location, "r")
                last_log_file_size = os.stat(log_file_location).st_size
        else:
            read_log_line(line, rsi_name, True, logger)


def start_tail_log_thread(log_file_location, rsi_name, logger):
    """Start the log tailing in a separate thread."""
    thread = threading.Thread(
        target=tail_log, args=(log_file_location, rsi_name, logger)
    )
    thread.daemon = True
    thread.start()


def is_game_running():
    """Check if Star Citizen is running."""
    return check_if_process_running("StarCitizen") is not None


def auto_shutdown(app, delay_in_seconds, logger=None):
    def shutdown():
        time.sleep(delay_in_seconds)
        if logger:
            logger.log(
                "Application has been open for 72 hours. Shutting down in 60 seconds."
            )
        else:
            print(
                "Application has been open for 72 hours. Shutting down in 60 seconds."
            )

        time.sleep(60)

        app.quit()
        sys.exit(0)

    # Run the shutdown logic in a separate thread
    shutdown_thread = threading.Thread(target=shutdown, daemon=True)
    shutdown_thread.start()


if __name__ == "__main__":
    game_running = is_game_running()

    app, logger = setup_gui(game_running)

    if game_running:
        # Start log monitoring in a separate thread
        log_file_location = set_sc_log_location()
        if log_file_location:
            rsi_handle = find_rsi_handle(log_file_location)
            find_rsi_geid(log_file_location)
            if rsi_handle:
                start_tail_log_thread(log_file_location, rsi_handle, logger)

    # Initiate auto-shutdown after 72 hours (72 * 60 * 60 seconds)
    if logger:
        auto_shutdown(app, 72 * 60 * 60, logger)  # Pass logger only if initialized
    else:
        auto_shutdown(app, 72 * 60 * 60)  # Fallback without logger

    app.mainloop()
