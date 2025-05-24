# test_bad.py
from main import safe_open

# 1. Create a file with a byte (0x90) invalid in cp1252
with open("bad.txt", "wb") as f:
    f.write(b"Hello\x90World")

# 2. Read it back through your helper
text = safe_open("bad.txt", "r").read()
print(text)
