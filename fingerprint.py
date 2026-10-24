"""
Fingerprint support for the Mantra MFS100 scanner.

The MFS100 has no macOS driver. On a Windows PC, install from https://mantratec.com/Drivers-SDK:
  1. "MFS100 Driver"
  2. "MFS100 Client Service"  (runs in the background, serves http://localhost:8004/mfs100/)
This module only talks to that local service, so no extra Python packages are needed.

Templates (ISO FMR, base64) are stored next to the student's face photos and never uploaded.
"""

import json
import os
import urllib.error
import urllib.request

import config

TEMPLATE_FILE = 'fingerprint.iso.txt'


class FingerprintError(Exception):
    pass


def enabled():
    return getattr(config, 'FINGERPRINT_ENABLED', False)


def _url(method):
    return getattr(config, 'FINGERPRINT_URL', 'http://localhost:8004/mfs100/') + method


def _call(method, payload=None, timeout=5):
    """GET (no payload) or POST JSON to the Mantra service; returns its JSON reply."""
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(_url(method), data=data,
                                 headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            reply = json.loads(resp.read().decode() or '{}')
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise FingerprintError(
            "Fingerprint service not reachable. Is the MFS100 plugged in and "
            f"'MFS100 Client Service' running? ({e})")
    if str(reply.get('ErrorCode', '0')) != '0':
        raise FingerprintError(reply.get('ErrorDescription') or f"Scanner error {reply.get('ErrorCode')}")
    return reply


def _capture_args():
    quality = getattr(config, 'FINGERPRINT_QUALITY', 60)
    timeout_ms = getattr(config, 'FINGERPRINT_TIMEOUT_MS', 10000)
    return {'Quality': quality, 'TimeOut': timeout_ms}, timeout_ms / 1000 + 5


def check_device():
    """Raise FingerprintError unless the service is up and a scanner is connected."""
    info = _call('info')
    return info.get('DeviceInfo') or info


def capture():
    """Wait for a finger on the scanner; return its ISO template (base64)."""
    args, timeout = _capture_args()
    reply = _call('capture', args, timeout=timeout)
    template = reply.get('IsoTemplate')
    if not template:
        raise FingerprintError('No fingerprint captured - place the finger flat on the scanner')
    return template


def verify(probe, gallery):
    """Compare two stored templates (no scanning)."""
    reply = _call('verify', {'ProbTemplate': probe, 'GalleryTemplate': gallery, 'BioType': 'FMR'})
    return bool(reply.get('Status'))


def scan_and_match(gallery):
    """Wait for a finger and check it against one student's template."""
    args, timeout = _capture_args()
    reply = _call('match', {**args, 'GalleryTemplate': gallery, 'BioType': 'FMR'}, timeout=timeout)
    return bool(reply.get('Status'))


def save_template(student_dir, template):
    with open(os.path.join(student_dir, TEMPLATE_FILE), 'w') as f:
        f.write(template)


def load_templates(dataset_path='dataset'):
    """{student_id: template} for every registered student who has a fingerprint."""
    templates = {}
    if not os.path.isdir(dataset_path):
        return templates
    for d in os.listdir(dataset_path):
        path = os.path.join(dataset_path, d, TEMPLATE_FILE)
        parts = d.split('_')
        if len(parts) > 1 and os.path.isfile(path):
            with open(path) as f:
                templates[parts[1].upper()] = f.read().strip()
    return templates


def wait_for_device():
    """Block until the scanner answers. Returns False if the user gives up."""
    while True:
        try:
            check_device()
            print("✅ Fingerprint scanner ready")
            return True
        except FingerprintError as e:
            print(f"\n🔌 {e}")
            answer = input("Connect the MFS100 fingerprint scanner, then press Enter to retry "
                           "(or 'q' to quit): ").strip().lower()
            if answer == 'q':
                return False
