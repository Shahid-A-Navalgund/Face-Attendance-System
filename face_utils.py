"""
Shared face helpers used by registration, training and attendance,
so every step detects and recognises faces the same way.

Detection: YuNet. Recognition: SFace (a deep-learning face embedding).
Both ship with OpenCV; only the model files are downloaded on first use.
"""

import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.request
import certifi
import cv2
import numpy as np

import config  # noqa: F401 - also switches to the project folder

MODELS_DIR = 'models'
_ZOO = 'https://github.com/opencv/opencv_zoo/raw/main/models/'
DETECTOR_MODEL = ('face_detection_yunet_2023mar.onnx', _ZOO + 'face_detection_yunet/')
RECOGNIZER_MODEL = ('face_recognition_sface_2021dec.onnx', _ZOO + 'face_recognition_sface/')

DETECT_WIDTH = 640            # detect on a downscaled frame for speed
SAVE_MARGIN = 0.35            # extra space kept around the face in saved photos
MODEL_PATH = 'trained_model/embeddings.npz'
LABELS_PATH = 'trained_model/labels.json'


def _model_file(name, base_url):
    path = os.path.join(MODELS_DIR, name)
    if not os.path.exists(path):
        os.makedirs(MODELS_DIR, exist_ok=True)
        print(f"⬇️  Downloading {name} (one time only)...")
        # certifi's CA bundle: python.org builds on macOS ship without trusted certificates
        ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(base_url + name, context=ctx) as resp, open(path + '.part', 'wb') as f:
            shutil.copyfileobj(resp, f)
        os.replace(path + '.part', path)
    return path


def gray_bgr(img):
    """Registration photos are stored grayscale, so live frames are matched in grayscale too."""
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


class FaceEngine:
    def __init__(self):
        self.detector = cv2.FaceDetectorYN.create(_model_file(*DETECTOR_MODEL), '', (320, 320), 0.7)
        self.recognizer = cv2.FaceRecognizerSF.create(_model_file(*RECOGNIZER_MODEL), '')

    def detect(self, img):
        """Return YuNet face rows (box + landmarks + score) in full-image coordinates, largest first."""
        scale = min(1.0, DETECT_WIDTH / img.shape[1])
        small = cv2.resize(img, None, fx=scale, fy=scale) if scale < 1 else img
        self.detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = self.detector.detect(small)
        if faces is None:
            return []
        faces[:, :14] /= scale
        return sorted(faces, key=lambda f: f[2] * f[3], reverse=True)

    def embed(self, img, face):
        """Unit-length SFace embedding of one detected face."""
        vec = self.recognizer.feature(self.recognizer.alignCrop(gray_bgr(img), face)).flatten()
        return vec / np.linalg.norm(vec)

    def embed_photo(self, gray):
        """Embedding of a saved registration photo (padded so tight crops still detect), or None."""
        img = gray_bgr(cv2.copyMakeBorder(gray, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=0))
        faces = self.detect(img)
        return self.embed(img, faces[0]) if faces else None


def face_crop(gray, face):
    """Grayscale crop of a detected face with some margin, for saving to the dataset."""
    x, y, w, h = face[:4]
    m = SAVE_MARGIN
    x0, y0 = int(max(0, x - m * w)), int(max(0, y - m * h))
    x1, y1 = int(min(gray.shape[1], x + w * (1 + m))), int(min(gray.shape[0], y + h * (1 + m)))
    return gray[y0:y1, x0:x1]


# Lists cameras in the exact order OpenCV numbers them on macOS (video + muxed, sorted by uniqueID)
_LIST_CAMERAS_SWIFT = '''
import AVFoundation
let devs = (AVCaptureDevice.devices(for: .video) + AVCaptureDevice.devices(for: .muxed)).sorted { $0.uniqueID < $1.uniqueID }
for d in devs { print("\\(d.deviceType.rawValue)\\t\\(d.localizedName)") }
'''
_camera_index = None


def _builtin_camera_index():
    """Index of the Mac's own camera, so a nearby iPhone (Continuity Camera) is never picked."""
    if sys.platform != 'darwin':
        return 0
    try:
        out = subprocess.run(['swift', '-'], input=_LIST_CAMERAS_SWIFT, capture_output=True,
                             text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        out = ''
    cams = [line.split('\t', 1) for line in out.splitlines() if '\t' in line]
    for i, (kind, name) in enumerate(cams):
        if 'BuiltIn' in kind and 'iPhone' not in name:
            print(f"📷 Using camera {i}: {name}")
            return i
    print("⚠️  Could not find the built-in camera, using camera 0 (set CAMERA_INDEX in config.py to choose)")
    return 0


def open_camera():
    """Open the built-in camera (or config.CAMERA_INDEX if set)."""
    global _camera_index
    if _camera_index is None:
        _camera_index = getattr(config, 'CAMERA_INDEX', None)
        if _camera_index is None:
            _camera_index = _builtin_camera_index()
    camera = cv2.VideoCapture(_camera_index)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return camera


def window_closed(name):
    """True once the user closes the camera window with its close button."""
    try:
        return cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:              # macOS raises once the window is gone
        return True


def focus_terminal():
    """macOS leaves keyboard focus on the closed camera window; hand it back to the terminal / VS Code."""
    app = os.environ.get('__CFBundleIdentifier')
    if sys.platform == 'darwin' and app:
        subprocess.run(['open', '-b', app], capture_output=True)


def save_labels(labels):
    """labels: {int label: {'id': ..., 'name': ...}} written next to the model."""
    os.makedirs(os.path.dirname(LABELS_PATH), exist_ok=True)
    with open(LABELS_PATH, 'w') as f:
        json.dump({str(k): v for k, v in labels.items()}, f, indent=2)


def load_labels():
    with open(LABELS_PATH) as f:
        return {int(k): v for k, v in json.load(f).items()}


def normalize(student_id, student_name):
    """IDs/names are stored uppercase: macOS folders ignore case, so '20231cit0113' and
    '20231CIT0113' would otherwise clash on disk but differ in Firebase."""
    return student_id.strip().upper(), ' '.join(student_name.split()).upper()


def mark_present(student_id, student_name, now):
    """Write today's attendance to Firebase. Returns the time already recorded today, or None if newly marked."""
    from firebase_admin import db
    ref = db.reference(f"attendance/{student_id}/{now:%d-%m-%Y}")
    existing = ref.get()
    if existing:
        return existing.get('time', '?')
    ref.set({'name': student_name, 'time': f'{now:%I:%M %p}', 'status': 'Present'})
    return None


def retrain():
    """Retrain the model from the whole dataset folder (module 02 starts with a digit, so import it by name)."""
    import importlib
    return importlib.import_module('02_train_model').FaceTrainer().train_recognizer()
