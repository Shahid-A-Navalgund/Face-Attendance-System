# Windows setup (face + fingerprint)

## 1. Install software
1. **Python 3.12** from https://www.python.org/downloads/ — tick **"Add python.exe to PATH"** in the installer.
2. **Git** from https://git-scm.com/download/win
3. **Mantra MFS100** from https://mantratec.com/Drivers-SDK → MFS100:
   - **MFS100 Driver**
   - **MFS100 Client Service** (the one for web/applications — *not* only "RD Service", that one is for Aadhaar and uses a different API)
   - Restart the laptop after installing.

## 2. Get the project
Open **PowerShell** (or Command Prompt):
```
git clone https://github.com/Shahid-A-Navalgund/Face-Attendance-System.git
cd Face-Attendance-System
```
Copy these two into the `Face-Attendance-System` folder (pen drive / Google Drive — never GitHub):
- `serviceAccountKey.json` (Firebase key)
- `dataset` folder (registered students' face photos)

## 3. Python environment
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
If PowerShell says *running scripts is disabled*, run this once, then activate again:
```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 4. Turn fingerprint on
Open `config.py` in Notepad and change:
```
FINGERPRINT_ENABLED = True
```

## 5. Connect the scanner
Plug the MFS100 into USB — its light should glow. Then:

| Step | Command |
|---|---|
| Add fingerprints for already-registered students (enter ID → `f`) and register new students | `python 01_face_registration.py` |
| Take attendance (face, then finger) | `python 03_mark_attendance.py` |
| Reports | `python 04_admin_dashboard.py` |

Every new PowerShell window: `cd` into the folder and run `venv\Scripts\activate` first.

## Troubleshooting
| Problem | Fix |
|---|---|
| "Fingerprint service not reachable" | Scanner plugged in? Light on? "MFS100 Client Service" installed and laptop restarted? Check *Services* app → Mantra service is *Running*. |
| Scanner works in Mantra's demo but not here | Mantra's software shows its URL (e.g. `https://localhost:8003/mfs100/`) — put it in `config.py` as `FINGERPRINT_URL`. |
| "FINGERPRINT NOT READ" | Press the finger flat, hold until done; clean the glass. Lower `FINGERPRINT_QUALITY` (e.g. 50) if it keeps failing. |
| Wrong / no camera | Set `CAMERA_INDEX = 0` (or 1) in `config.py`. |
| Face-only without scanner | `FINGERPRINT_ENABLED = False` |
