# 🏴‍☠️ BeowulfHunter

**A Star Citizen kill tracker and combat logger for the pirate org IronPoint.**

![beohunter](https://github.com/user-attachments/assets/64815013-ecfb-4797-9a27-2ab7c89f0f1a)


---

## ⚙️ Features

- ✅ Real-time log monitoring
- ☠️ Kill detection
- 📦 Auto-submission to API and Database
- 📊 Leaderboard through the Discord bot Beowulf
- 💀 Pirate-themed interface

---

## 🚀 Getting Started

1. You can download the precompiled .exe and run without installation, or...
2. You can ```git clone``` the codebase and compile it yourself.
3. Retrieve an API key from Beowulf on the IronPoint Discord Server

### 📦 Installation

```bash
git clone https://github.com/yourname/BeowulfHunter.git
cd BeowulfHunter
npm install
npm start
```

### 💾 Information being Tracked

  - ❌ IP Addresses
  - ✅ Username associated with kill
  - ✅ Victim's name
  - ✅ Ship used (sometimes)
  - ✅ Ship killed (sometimes)
  - ✅ Dollar Value of Killed Ship
  - ❌ Player Location

Which can be verified in the code, itself.
  - There is a "zone" tracked in the code, but the zone correlates to where the player is sitting when they make the kill. For most cases, this is the ship itself. This can be chalked up to CiG being bad with naming conventions. There ARE coordinates given in the kill log, but I disregard these.
  - Example kill log:

```<2025-04-13T17:17:51.279Z> [Notice] <Actor Death> CActor::Kill: 'Mercuriuss' [200146297631] in zone 'ANVL_Hornet_F7A_Mk2_2677329226210' killed by 'DocHound' [202061381370] using 'GATS_BallisticGatling_S3_2677329225797' [Class unknown] with damage type 'VehicleDestruction' from direction x: 0.000000, y: 0.000000, z: 0.000000 [Team_ActorTech][Actor]```
