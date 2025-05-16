from time import sleep
from os import stat
from threading import Thread


class LogParser:
    """Parses the game.log file for Star Citizen."""

    def __init__(
        self,
        gui_module,
        api_client_module,
        sound_module,
        cm_module,
        local_version,
        monitoring,
        rsi_handle,
        player_geid,
        active_ship,
        anonymize_state,
    ):
        # gui_module is actually your EventLogger
        self.log = gui_module
        # keep self.gui pointing at the same logger if you want
        self.gui = gui_module
        self.api = api_client_module
        self.sounds = sound_module
        self.cm = cm_module
        self.local_version = local_version
        self.monitoring = monitoring
        self.rsi_handle = rsi_handle
        self.active_ship = active_ship
        self.anonymize_state = anonymize_state
        self.game_mode = "Nothing"
        self.active_ship_id = "N/A"
        self.player_geid = player_geid
        self.log_file_location = None
        ##self.curr_killstreak = 0
        ##self.max_killstreak = 0
        ##self.kill_total = 0

        self.global_ship_list = [
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
        # Substrings to ignore
        self.ignore_kill_substrings = [
            "PU_Pilots",
            "NPC_Archetypes",
            "PU_Human",
            "kopion",
            "marok",
        ]

    def start_tail_log_thread(self) -> None:
        """Start the log tailing in a separate thread only if it's not already running."""
        thr = Thread(target=self.tail_log, daemon=True)
        thr.start()

    def tail_log(self) -> None:
        """Read the log file and display events in the GUI."""
        try:
            sc_log = open(self.log_file_location, "r")
            if sc_log is None:
                self.log.log(f"No log file found at {self.log_file_location}")
                return
        except Exception as e:
            self.log.log(f"Error opening log file: {e.__class__.__name__} {e}")
        try:
            self.log.log("Enter Kill Tracker Key to establish Servitor connection...")
            sleep(1)
            while self.monitoring["active"]:
                # Block loop until API key is valid
                if self.api.api_key["value"]:
                    break
                sleep(1)
            self.log.debug(
                f"tail_log(): Received key: {self.api.api_key}. Moving on..."
            )
        except Exception as e:
            self.log.log(
                f"Error waiting for Servitor connection to be established: {e.__class__.__name__} {e}"
            )

        try:
            # Read all lines to find out what game mode player is currently, in case they booted up late.
            # Don't upload kills, we don't want repeating last session's kills in case they are actually available.
            self.log.info(
                "Loading old log (if available)! Note that old kills shown will not be uploaded as they are stale."
            )
            lines = sc_log.readlines()
            for line in lines:
                if not self.api.api_key["value"]:
                    self.log.log("Error: key is invalid. Loading old log stopped.")
                    break
                self.read_log_line(line, False)
        except Exception as e:
            self.log.log(f"Error reading old log file: {e.__class__.__name__} {e}")

        try:
            # Main loop to monitor the log
            last_log_file_size = stat(self.log_file_location).st_size
            self.log.debug(f"tail_log(): Last log size: {last_log_file_size}.")
            self.log.success("Kill Tracking initiated.")
            self.log.success("Go Forth And Slaughter...")
        except Exception as e:
            self.log.log(f"Error getting log file size: {e.__class__.__name__} {e}")

        while self.monitoring["active"]:
            try:
                if not self.api.api_key["value"]:
                    self.log.log(
                        "Error: key is invalid. Kill Tracking is not active..."
                    )
                    sleep(5)
                    continue
                where = sc_log.tell()
                line = sc_log.readline()
                if not line:
                    sleep(1)
                    sc_log.seek(where)
                    if last_log_file_size > stat(self.log_file_location).st_size:
                        sc_log.close()
                        sc_log = open(self.log_file_location, "r")
                        last_log_file_size = stat(self.log_file_location).st_size
                else:
                    self.read_log_line(line, True)
            except Exception as e:
                self.log.log(f"Error reading game log file: {e.__class__.__name__} {e}")
        self.log.info("Game log monitoring has stopped.")

    def read_log_line(self, line: str, upload_kills: bool) -> None:
        """Event checking logic. Look for substrings, do stuff based on what we find."""
        if line.find("<Context Establisher Done>") != -1:
            self.set_game_mode(line)
            self.log.debug(f"read_log_line(): set_game_mode with: {line}.")
        elif (
            line.find("CPlayerShipRespawnManager::OnVehicleSpawned") != -1
            and self.game_mode != "SC_Default"
            and line.find(self.player_geid["current"]) != -1
        ):
            self.set_ac_ship(line)
            self.log.debug(f"read_log_line(): set_ac_ship with: {line}.")
        elif (
            line.find("<Vehicle Destruction>") != -1
            or line.find("<local client>: Entering control state dead") != -1
        ) and line.find(self.active_ship_id) != -1:
            # Send ship destroy event to the server via heartbeat
            self.log.debug(f"read_log_line(): destroy_player_zone with: {line}")
            self.destroy_player_zone()
        elif line.find(self.rsi_handle["current"]) != -1:
            # NOTE: OnEntityEnterZone not current in logs
            if line.find("OnEntityEnterZone") != -1:
                # Send change ship event to the server via heartbeat
                self.log.debug(f"read_log_line(): set_player_zone with: {line}.")
                self.set_player_zone(line, False)
            if (
                line.find("CActor::Kill") != -1
                and not self.check_substring_list(line, self.ignore_kill_substrings)
                and upload_kills
            ):
                kill_result = self.parse_kill_line(line, self.rsi_handle["current"])
                self.log.debug(f"read_log_line(): kill_result with: {line}.")
                if kill_result["result"] in ("exclusion", "reset"):
                    self.log.debug(
                        f"read_log_line(): Not posting {kill_result['result']} death: {line}."
                    )
                    return
                # simplified: just report death or kill
                if kill_result["result"] in ("killed", "suicide"):
                    # you died
                    self.api.post_death_event(kill_result["data"])
                    self.destroy_player_zone()
                elif kill_result["result"] == "killer":
                    # you killed someone
                    self.sounds.play_random_sound()
                    self.api.post_kill_event(kill_result)
                else:
                    self.log.log(f"Kill failed to parse: {line}")
        elif line.find("<Jump Drive State Changed>") != -1:
            self.log.debug(f"read_log_line(): set_player_zone with: {line}.")
            self.set_player_zone(line, True)
            ## WILL POSSIBLY USE LATER
            ##if kill_result["result"] in ("killed", "suicide"):
            ##self.curr_killstreak = 0
            ##self.gui.curr_killstreak_label.config(
            ##text=f"Current Killstreak: {self.curr_killstreak}", fg="yellow"
            ##)
            ##self.log.info("You have fallen in the service of BlightVeil.")
            # send *you died* to the backend
            ##self.api.post_death_event(kill_result["data"])
            ##self.destroy_player_zone()
            ##elif kill_result["result"] == "killer":
            ##self.curr_killstreak += 1
            ##self.max_killstreak = max(self.max_killstreak, self.curr_killstreak)
            ##self.kill_total += 1
            ##self.gui.curr_killstreak_label.config(
            ##text=f"Current Killstreak: {self.curr_killstreak}", fg="yellow"
            ##)
            ##self.gui.max_killstreak_label.config(
            ##text=f"Max Killstreak: {self.max_killstreak}", fg="yellow"
            ##)
            ##self.gui.session_kills_label.config(
            ##text=f"Total Session Kills: {self.kill_total}", fg="yellow"
            ##)
            ##self.log.success(
            ##f"You have killed {kill_result['data']['victim']},"
            ##)
            ##self.log.info("and brought glory to BlightVeil.")
            ##self.sounds.play_random_sound()
            ##self.api.post_kill_event(kill_result)

    def set_game_mode(self, line: str) -> None:
        """Parse log for current active game mode."""
        split_line = line.split(" ")
        curr_game_mode = split_line[8].split("=")[1].strip('"')
        if curr_game_mode != self.game_mode:
            self.game_mode = curr_game_mode
        if self.game_mode == "SC_Default":
            self.active_ship["current"] = "N/A"
            self.active_ship_id = "N/A"

    def set_ac_ship(self, line: str) -> None:
        """Parse log for current active ship."""
        self.active_ship["current"] = line.split(" ")[5][1:-1]
        self.log.debug(f"Player has entered ship: {self.active_ship['current']}")

    def destroy_player_zone(self) -> None:
        """Remove current active ship zone."""
        if self.active_ship["current"] != "N/A" or self.active_ship_id != "N/A":
            self.log.debug(
                f"Ship Destroyed: {self.active_ship['current']} with ID: {self.active_ship_id}"
            )
            self.active_ship["current"] = "N/A"
            self.active_ship_id = "N/A"

    def set_player_zone(self, line: str, use_jd) -> None:
        """Set current active ship zone."""
        if not use_jd:
            line_index = line.index("-> Entity ") + len("-> Entity ")
        else:
            line_index = line.index("adam: ") + len("adam: ")
        if line_index < 0:
            self.log.debug(f"Active Zone Change: {self.active_ship['current']}")
            self.active_ship["current"] = "N/A"
            return
        potential_zone = line[line_index:].split(" ")[0].strip("[]'(")
        for ship in self.global_ship_list:
            if potential_zone.startswith(ship):
                parts = potential_zone.rsplit("_", 1)
                self.active_ship["current"], self.active_ship_id = parts[0], parts[1]
                self.log.debug(
                    f"Active Zone Change: {self.active_ship['current']} with ID: {self.active_ship_id}"
                )
                self.cm.post_heartbeat_enter_ship_event(self.active_ship["current"])
                return

    def check_substring_list(self, line, substring_list: list) -> bool:
        """Check if any substring from the list is present in the given line."""
        return any(substr.lower() in line.lower() for substr in substring_list)

    def check_exclusion_scenarios(self, line: str) -> bool:
        """Check for kill edgecase scenarios."""
        if self.game_mode.startswith("EA_"):
            if any(x in line for x in ("Crash", "SelfDestruct")):
                self.log.info("Ignoring reset/destruct in AC mode")
                return False
        return True

    def parse_kill_line(self, line: str, curr_user: str):
        ##Parse kill event.
        try:
            if not self.check_exclusion_scenarios(line):
                return {"result": "exclusion", "data": None}

            # ─── split out time, actors, ships, damage ────────────────────────
            parts = line.split(" ")
            kill_time = parts[0].strip("<>")
            killed = parts[5].strip("'")
            killed_geid = parts[6].strip("[]")
            killed_zone = parts[9].strip("'")
            killer = parts[12].strip("'")
            weapon = parts[15].strip("'")
            damage = parts[21].strip("'")

            # ─── build common fields ────────────────────────────────────────
            rsi_profile = f"https://robertsspaceindustries.com/citizens/{killed}"
            # decide if killed_zone is actually a ship or a real location
            is_ship = any(killed_zone.startswith(s) for s in self.global_ship_list)
            if is_ship:
                # zone was a ship code
                victim_ship = killed_zone.rsplit("_", 1)[0]
                data_zone = "N/A"
            else:
                # not a ship → no victim ship, real location
                victim_ship = "N/A"
                data_zone = killed_zone

            # ─── decide result and shape data ────────────────────────────────
            if killed == killer:
                return {
                    "result": "suicide",
                    "data": {
                        "player": curr_user,
                        "time": kill_time,
                        "zone": killed_zone,
                    },
                }
            elif killed == curr_user:
                return {
                    "result": "killed",
                    "data": {
                        "killer": killer,
                        "victim": curr_user,
                        "time": kill_time,
                        "zone": data_zone,
                        "weapon": weapon,
                        "damage_type": damage,
                        "rsi_profile": f"https://robertsspaceindustries.com/citizens/{killer}",
                        "game_mode": self.game_mode,
                        "mode": (
                            "ac-kill" if self.game_mode.startswith("EA_") else "pu-kill"
                        ),
                        "killers_ship": "N/A",
                        "victim_ship": victim_ship,
                    },
                }
            elif killer.lower() == "unknown":
                return {"result": "reset", "data": {}}
            else:
                return {
                    "result": "killer",
                    "data": {
                        "player": curr_user,
                        "victim": killed,
                        "time": kill_time,
                        "zone": data_zone,
                        "weapon": weapon,
                        "damage_type": damage,
                        "rsi_profile": rsi_profile,
                        "game_mode": self.game_mode,
                        "mode": (
                            "ac-kill" if self.game_mode.startswith("EA_") else "pu-kill"
                        ),
                        "client_ver": self.local_version,
                        "killers_ship": self.active_ship["current"],
                        "victim_ship": victim_ship,
                        "anonymize_state": self.anonymize_state,
                    },
                }

        except Exception as e:
            self.log.log(f"parse_kill_line(): Error: {e}")
            return {"result": "error", "data": None}

    def find_rsu_handle(self) -> str:
        """Get the current user's RSI handle."""
        acct_str = "<Legacy login response> [CIG-net] User Login Success"
        with open(self.log_file_location, "r") as sc_log:
            for line in sc_log:
                if acct_str in line:
                    idx = line.index("Handle[") + len("Handle[")
                    handle = line[idx:].split(" ")[0].rstrip("]")
                    return handle
        return ""

    def find_rsi_geid(self) -> str:
        """Get the current user's GEID."""
        acct_kw = "AccountLoginCharacterStatus_Character"
        with open(self.log_file_location, "r") as sc_log:
            for line in sc_log:
                if acct_kw in line:
                    return line.split(" ")[11]
