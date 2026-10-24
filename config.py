# Firebase settings - replace with your project's values
FIREBASE_DATABASE_URL = "https://attendance-system-40483-default-rtdb.asia-southeast1.firebasedatabase.app/"
SERVICE_ACCOUNT_KEY = "serviceAccountKey.json"

# Face match cutoff (similarity 0-1, higher = closer match). Lower it if registered
# students show as "Unknown", raise it if the wrong student gets matched.
MATCH_THRESHOLD = 0.5

# Camera to use. None = auto-pick the Mac's built-in camera (never a nearby iPhone).
# Set a number (0, 1, ...) to force a specific camera.
CAMERA_INDEX = None

# Fingerprint scanner (Mantra MFS100) - works on Windows only, see fingerprint.py for setup.
# True = registration takes a fingerprint and attendance needs face AND fingerprint.
# Set False to run face-only (e.g. on a Mac).
FINGERPRINT_ENABLED = False
FINGERPRINT_URL = "auto"          # or e.g. "https://localhost:8003/mfs100/"
FINGERPRINT_QUALITY = 60          # minimum scan quality (0-100)
FINGERPRINT_TIMEOUT_MS = 10000    # how long to wait for a finger
