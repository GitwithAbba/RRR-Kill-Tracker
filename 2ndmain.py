2ndmain.py

import os
import json
import psutil
import requests
import threading
import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext
import time
import re
from datetime import datetime, timedelta
from config import BACKEND_URL, VALIDATE_URL, REPORT_KILL_URL, REPORT_DEATH_URL


class LogParser:
    def __init__(self, api_key_ref, player_geid_ref, gui_logger):
        self.api_key_ref = api_key_ref
        self.player_geid_ref = player_geid_ref
        self.logger = gui_logger
        self.game_mode = "Nothing"
        self.active_ship = "N/A"
        self.active_ship_id = "N/A"
        self.active_zone = "Unknown"
        self.zone_by_geid = {}
        self.ignore_list = ["PU_Pilots", "NPC_Archetypes", "PU_Human", "kopion", "marok"]
        self.ship_rx = re.compile(r"([A-Z0-9]+_[A-Za-z0-9]+)_\d+")

    def set_game_mode(self, line):
        parts = line.split()
        mode = parts[8].split('=')[1].strip('"')
        if mode != self.game_mode:
            self.game_mode = mode
            self.active_ship = "N/A"
            self.active_ship_id = "N/A"
            self.logger.log(f"🔄 Game Mode: {mode}")

    def on_entity_enter_zone(self, line):
        m = re.search(r"OnEntityEnterZone.*?Zone \['([^']+)'\].*?Entity \[(\d+)\]", line)
        if not m: return
        zone_str, geid = m.groups()
        self.active_zone = zone_str
        self.logger.log(f"🌐 Entered Zone: {zone_str}")
        code = zone_str.rsplit('_', 1)[0]
        self.zone_by_geid[geid] = code
        if geid == self.player_geid_ref['current']:
            self.active_ship, self.active_ship_id = zone_str.rsplit('_', 1)
            self.logger.log(f"🚀 Active Ship: {self.active_ship}")

    def on_vehicle_spawned(self, line):
        if self.player_geid_ref['current'] not in line: return
        m = re.search(r"OnVehicleSpawned.*\[([A-Z0-9_]+_\d+)\]", line)
        if not m: return
        full = m.group(1); ship, _, sid = full.rpartition('_')
        self.active_ship, self.active_ship_id = ship, sid
        self.logger.log(f"🚀 Respawn Ship: {ship}")

    def on_jump_drive(self, line):
        m = re.search(r"\(adam:\s*([A-Z0-9]+_[A-Za-z0-9]+)\b", line)
        if not m: return
        ship_id = m.group(1)
        ship, sid = ship_id.rsplit('_',1)
        self.active_ship, self.active_ship_id = ship, sid
        self.logger.log(f"🚀 Jump Ship: {ship}")

    def on_destroy(self, line):
        if '<Vehicle Destruction>' in line or '<local client>: Entering control state dead' in line:
            self.active_ship, self.active_ship_id = 'N/A', 'N/A'
            self.logger.log("💥 Ship/Player destroyed, cleared active_ship")

    def parse_kill_line(self, line):
        if 'CActor::Kill' not in line or self.player_geid_ref['current'] not in line:
            return
        parts = line.split()
        killed, killed_geid = parts[5].strip("'"), parts[6].strip('[]')
        killer, killer_geid = parts[12].strip("'"), parts[13].strip('[]')
        weapon = parts[15].strip("'")
        dmg = parts[-8].strip('"')  # adjust index if needed
        time_str = parts[0].strip('<>')
        zone = self.active_zone.rsplit('_',1)[0]

        # determine death vs kill
        if killed == self.player_geid_ref['current']:
            payload = {
                'killer': killer,
                'victim': killed,
                'time': time_str,
                'zone': zone,
                'weapon': weapon,
                'damage_type': dmg
            }
            self.logger.log(f"→ DEATH payload: {payload}")
            requests.post(REPORT_DEATH_URL, headers={'Authorization':f"Bearer {self.api_key_ref['value']}"}, json=payload)
            self.logger.log("You DIED.")
        else:
            payload = {
                'player': self.player_geid_ref['current'],
                'victim': killed,
                'time': time_str,
                'zone': zone,
                'weapon': weapon,
                'damage_type': dmg,
                'killers_ship': self.active_ship,
                'victim_ship': self.zone_by_geid.get(killed_geid,'N/A')
            }
            self.logger.log(f"→ KILL payload: {payload}")
            r = requests.post(REPORT_KILL_URL, headers={'Authorization':f"Bearer {self.api_key_ref['value']}"}, json=payload)
            if r.status_code in (200,201): self.logger.log("✅ Kill recorded")

    def read_line(self, line):
        # hook order
        if '<Context Establisher Done>' in line: self.set_game_mode(line)
        if '<Jump Drive State Changed>' in line: self.on_jump_drive(line)
        if 'OnEntityEnterZone' in line: self.on_entity_enter_zone(line)
        if 'OnVehicleSpawned' in line: self.on_vehicle_spawned(line)
        self.on_destroy(line)
        if 'CActor::Kill' in line: self.parse_kill_line(line)


def tail_log(path, parser):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1); continue
            parser.read_line(line)

# GUI setup omitted for brevity

if __name__ == '__main__':
    # locate Game.log, read player handle and GEID, instantiate parser
    game_log = find_game_log()
    rsi_handle = extract_handle(game_log)
    player_geid = {'current': extract_geid(game_log)}
    api_key = {'value': load_api_key()}

    gui = setup_gui()
    parser = LogParser(api_key, player_geid, gui.logger)
    threading.Thread(target=tail_log, args=(game_log, parser), daemon=True).start()
    gui.app.mainloop()
