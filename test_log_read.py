# test_log_read.py
from main import safe_open

# Replace this path with the exact path your friend’s game writes to:
log_path = r"C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log"

try:
    with safe_open(log_path, "r") as f:
        # Read and print the first few lines
        for _ in range(10):
            print(f.readline().rstrip())
except Exception as e:
    print("Still hit an error:", repr(e))
