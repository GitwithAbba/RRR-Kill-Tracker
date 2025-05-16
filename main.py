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
import re
from typing import Dict
from config import BACKEND_URL, API_KEY, VALIDATE_URL, REPORT_KILL_URL, REPORT_DEATH_URL
from log_parser import LogParser
from api_client import APIClient
from helpers import play_kill_sound, resource_path


class NullCM:
    def post_heartbeat_enter_ship_event(self, ship):
        pass

    def post_heartbeat_death_event(self, player, zone):
        pass


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

SHIP_RX = re.compile(r"([A-Z0-9]+_[A-Za-z0-9]+)_\d+")
ON_SPAWN_RX = re.compile(r"OnVehicleSpawned.*?\(([^)]+)\)\s*by player\s*(\d+)")


def is_game_running():
    return check_if_process_running("StarCitizen") is not None


class CMClient:
    def post_heartbeat_enter_ship_event(self, ship):
        # TODO: hook into your existing “enter‐ship” heartbeat
        pass

    def post_heartbeat_death_event(self, player, zone):
        # TODO: hook into your existing “death” heartbeat
        pass


cm = CMClient()
# ──────────────────────────────────────────────────────────────────────────


# ─── Helpers ────────────────────────────────────────────────────────────────────
def find_rsi_handle(log_file_location):
    acct_str = "<Legacy login response> [CIG-net] User Login Success"
    with open(log_file_location, "r", encoding="utf-8", errors="replace") as sc_log:
        for line in sc_log:
            if acct_str in line:
                idx = line.index("Handle[") + len("Handle[")
                return line[idx:].split(" ")[0].rstrip("]")
    return None


def find_rsi_geid(log_file_location):
    global global_player_geid
    acct_kw = "AccountLoginCharacterStatus_Character"
    with open(log_file_location, "r", encoding="utf-8", errors="replace") as sc_log:
        for line in sc_log:
            if acct_kw in line:
                global_player_geid = line.split(" ")[11]
                return global_player_geid
    return None


def safe_open(path, mode="r"):
    """
    Open text files in UTF-8 and fall back to replacing bad chars
    rather than crashing on UnicodeDecodeError.
    Supports read ('r'), write ('w'), append ('a'), etc.
    """
    if "w" in mode or "a" in mode:
        return open(path, mode, encoding="utf-8")
    # reading modes get error-replace
    return open(path, mode, encoding="utf-8", errors="replace")


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

    # alias the other levels back to .log()
    def debug(self, m):
        self.log(f"[DEBUG] {m}")

    def info(self, m):
        self.log(f"[INFO] {m}")

    def warning(self, m):
        self.log(f"[WARNING] {m}")

    def error(self, m):
        self.log(f"[ERROR] {m}")

    def success(self, m):
        self.log(f"[SUCCESS] {m}")


def show_loading_animation(logger, app):
    for dots in [".", "..", "..."]:
        logger.log(dots)
        app.update_idletasks()
        time.sleep(0.2)


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
    with safe_open("killtracker_key.cfg", "w") as f:
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
class SoundsAdapter:
    def __init__(self, logger):
        self.log = logger

    def play_random_sound(self):
        play_kill_sound()


def setup_gui(game_running):
    app = tk.Tk()
    app.title("RRRthur Tracker")
    app.geometry("650x450")
    app.resizable(False, False)
    app.configure(bg="#1a1a1a")

    try:
        font_path = resource_path("Orbitron.ttf")
        custom_font = tkFont.Font(family="Orbitron", size=12)
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
                with safe_open("killtracker_key.cfg", "r") as f:
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


if __name__ == "__main__":
    # 1) launch GUI & get logger
    app, logger = setup_gui(is_game_running())

    # 2) find the SC log file
    log_file_location = set_sc_log_location()
    if not log_file_location:
        app.mainloop()
        sys.exit(0)

    # 3) grab your RSI handle & GEID
    rsi_handle = find_rsi_handle(log_file_location)
    find_rsi_geid(log_file_location)
    player_geid = global_player_geid

    # 4) wire up support modules
    api = APIClient(api_key)
    sounds = SoundsAdapter(logger)  # <— only here, after logger exists
    cm = NullCM()

    # 5) start the unified LogParser
    monitoring = {"active": True}
    parser = LogParser(
        gui_module=logger,
        api_client_module=api,
        sound_module=sounds,
        cm_module=cm,
        local_version=local_version,
        monitoring=monitoring,
        rsi_handle={"current": rsi_handle},
        player_geid={"current": player_geid},
        active_ship={"current": global_active_ship},
        anonymize_state=False,
    )
    parser.log_file_location = log_file_location
    parser.start_tail_log_thread()

    app.mainloop()
