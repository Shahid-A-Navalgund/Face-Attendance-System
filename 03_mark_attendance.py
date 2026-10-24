"""
MODULE 3: ATTENDANCE MARKING SYSTEM
Real-time face recognition and attendance marking
"""

import cv2
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import numpy as np
import pytz
import firebase_admin
from firebase_admin import credentials
import config
import face_utils
import fingerprint

class AttendanceMarker:
    REQUIRED_FRAMES = 5       # same student must be matched this many frames in a row
    MARGIN = 0.10             # best student must beat the runner-up by this much, else 'Unknown'
    MIN_FACE = 100            # px; smaller (far away / background) faces are too blurry to trust

    def __init__(self, model_path=face_utils.MODEL_PATH):
        self.engine = face_utils.FaceEngine()
        self.model_path = model_path
        self.student_labels = {}
        self.marked_today = {}
        self.streaks = {}
        self.banner = (None, None, 0.0)   # (text, colour, when) shown mid-screen for a moment
        # Face AND fingerprint: after the face is verified, that student's finger is scanned here
        # in the background so the video keeps running while the scanner waits
        self.finger_pool = ThreadPoolExecutor(max_workers=1)
        self.pending = None               # (label, student_id, name, future) while a scan runs
        self.templates = {}
        self.timezone = pytz.timezone('Asia/Kolkata')
        # Firebase writes run here so the camera never freezes waiting on the network
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.firebase_ready = False

        # Initialize Firebase
        try:
            firebase_admin.get_app()
            self.firebase_ready = True
        except ValueError:
            try:
                cred = credentials.Certificate(config.SERVICE_ACCOUNT_KEY)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': config.FIREBASE_DATABASE_URL
                })
                self.firebase_ready = True
                print("✅ Firebase connected successfully!")
            except Exception as e:
                print(f"⚠️ Firebase error: {e}")

        # Students registered since the last training run wouldn't be recognised, so retrain first
        changed = self._changed_student_folders()
        if changed:
            print(f"🔄 {len(changed)} student folder(s) changed since the last training - retraining...")
            face_utils.retrain()

        # Load the trained model and the label mapping saved with it
        if os.path.exists(model_path) and os.path.exists(face_utils.LABELS_PATH):
            data = np.load(model_path)
            self.embeddings, self.labels = data['embeddings'], data['labels']
            self.student_labels = face_utils.load_labels()
            print(f"✅ Model loaded: {len(self.student_labels)} students")
        else:
            print(f"❌ Trained model not found")
            print("📌 Register students first using 01_face_registration.py")

    def _changed_student_folders(self):
        if not os.path.isdir('dataset'):
            return []
        if not (os.path.exists(self.model_path) and os.path.exists(face_utils.LABELS_PATH)):
            return ['(no model yet)']
        model_time = os.path.getmtime(self.model_path)
        trained = {info['id'] for info in face_utils.load_labels().values()}
        changed = []
        for d in os.listdir('dataset'):
            path = os.path.join('dataset', d)
            if not os.path.isdir(path) or not os.listdir(path):
                continue
            parts = d.split('_')
            student_id = parts[1].upper() if len(parts) > 1 else d
            if os.path.getmtime(path) > model_time or student_id not in trained:
                changed.append(d)
        return changed

    def mark_attendance(self, student_id, student_name):
        """Record locally right away, save to Firebase in the background."""
        now = datetime.now(self.timezone)
        date_str = now.strftime('%d-%m-%Y')

        if self.marked_today.get(student_id, {}).get('date') == date_str:
            return False

        time_str = now.strftime('%I:%M %p')
        self.marked_today[student_id] = {
            'name': student_name,
            'date': date_str,
            'time': time_str
        }

        if self.firebase_ready:
            self.pool.submit(self._save_to_firebase, student_id, student_name, date_str, time_str)
        else:
            print(f"✅ MARKED (offline, not saved to Firebase): {student_name} (ID: {student_id}) at {time_str}")
        return True

    def _save_to_firebase(self, student_id, student_name, date_str, time_str):
        try:
            earlier = face_utils.mark_present(student_id, student_name, datetime.now(self.timezone))
            if earlier:
                print(f"ℹ️  {student_name} (ID: {student_id}) was already marked today at {earlier}")
                self.marked_today[student_id]['time'] = earlier
                return
            print(f"✅ MARKED: {student_name} (ID: {student_id}) at {time_str}")
        except Exception as e:
            # Forget the local mark so the student is retried next time they're seen
            self.marked_today.pop(student_id, None)
            print(f"⚠️  Error saving attendance for {student_name}: {e}")

    def identify(self, vec, threshold):
        """Return (label or None, score). A student's score is the mean similarity of their
        3 closest photos; an unregistered face is 'Unknown' instead of its nearest student."""
        sims = self.embeddings @ vec
        scores = sorted(((np.sort(sims[self.labels == label])[-3:].mean(), label)
                         for label in self.student_labels), reverse=True)
        score, label = scores[0]
        runner_up = scores[1][0] if len(scores) > 1 else -1.0
        if score >= threshold and score - runner_up >= self.MARGIN:
            return label, score
        return None, score

    def _show(self, text, colour):
        self.banner = (text, colour, time.time())

    def _face_verified(self, label, student_id, student_name):
        """Face matched long enough: mark (face-only) or start the fingerprint check."""
        if not fingerprint.enabled():
            self.mark_attendance(student_id, student_name)
            self._show(f'{student_name} MARKED - NEXT STUDENT', (0, 120, 0))
            return
        template = self.templates.get(student_id)
        if not template:
            self._show(f'{student_name}: NO FINGERPRINT REGISTERED', (0, 0, 160))
            self.streaks.pop(label, None)
            return
        future = self.finger_pool.submit(fingerprint.scan_and_match, template)
        self.pending = (label, student_id, student_name, future)

    def _check_fingerprint(self):
        """Finish a fingerprint scan once the scanner has answered."""
        label, student_id, student_name, future = self.pending
        if not future.done():
            return
        self.pending = None
        self.streaks.pop(label, None)     # face must be verified again for another attempt
        try:
            matched = future.result()
        except fingerprint.FingerprintError as e:
            print(f"⚠️  Fingerprint: {e}")
            self._show('FINGERPRINT NOT READ - TRY AGAIN', (0, 0, 160))
            return
        if matched:
            self.mark_attendance(student_id, student_name)
            self._show(f'{student_name} MARKED - NEXT STUDENT', (0, 120, 0))
        else:
            print(f"❌ Fingerprint did not match {student_name} ({student_id})")
            self._show(f'FINGERPRINT DOES NOT MATCH {student_name}', (0, 0, 160))

    def start_recognition(self, confidence_threshold=None):
        if confidence_threshold is None:
            confidence_threshold = getattr(config, 'MATCH_THRESHOLD', 0.5)

        if not self.student_labels:
            print("❌ Model not loaded! Train the model first.")
            return

        if fingerprint.enabled():
            if not fingerprint.wait_for_device():
                return
            self.templates = fingerprint.load_templates()
            missing = [i['name'] for i in self.student_labels.values() if i['id'] not in self.templates]
            if missing:
                print(f"⚠️  No fingerprint registered for: {', '.join(missing)}")
                print("   They can't mark attendance until added (01_face_registration.py → same ID → 'f')")

        camera = face_utils.open_camera()

        if not camera.isOpened():
            print("❌ Cannot open camera!")
            print("📌 macOS: System Settings → Privacy & Security → Camera → allow your terminal/VS Code")
            return

        print("\n" + "="*70)
        print("📹 ATTENDANCE MARKING - REAL-TIME FACE RECOGNITION")
        print("="*70)
        print("📌 Instructions:")
        print("   • One student at a time: look at the camera and hold still for a moment")
        if fingerprint.enabled():
            print("   • When asked on screen, place your finger on the fingerprint scanner")
        print("   • When 'MARKED - NEXT STUDENT' appears, the next student steps up")
        print("   • Yellow box = verifying, green box = attendance marked")
        print("   • Press 'q' to quit")
        print("="*70 + "\n")

        window = 'Attendance System - Face Recognition'
        failed_reads = 0
        while True:
            ret, frame = camera.read()

            if not ret:
                failed_reads += 1          # camera may need a moment to warm up
                if failed_reads > 50:
                    print("❌ Cannot read frame from camera!")
                    break
                cv2.waitKey(20)
                continue
            failed_reads = 0

            frame = cv2.flip(frame, 1)
            seen = set()
            if self.pending:
                self._check_fingerprint()

            for face in self.engine.detect(frame):
                x, y, w, h = face[:4].astype(int)
                if w < self.MIN_FACE:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (160, 160, 160), 2)
                    cv2.putText(frame, 'come closer', (x, y-8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (160, 160, 160), 2)
                    continue
                label, score = self.identify(self.engine.embed(frame, face), confidence_threshold)
                info = self.student_labels.get(label)

                if info:
                    seen.add(label)
                    self.streaks[label] = self.streaks.get(label, 0) + 1
                    student_id, student_name = info['id'], info['name']

                    if student_id in self.marked_today:
                        color, text = (0, 255, 0), f'{student_name} - marked'
                    elif self.pending and self.pending[0] == label:
                        color, text = (255, 200, 0), f'{student_name} - PLACE FINGER ON SCANNER'
                    elif self.pending:
                        color, text = (0, 200, 255), f'{student_name} - please wait'
                    elif self.streaks[label] >= self.REQUIRED_FRAMES:
                        self._face_verified(label, student_id, student_name)
                        color, text = (255, 200, 0), f'{student_name} - checking...'
                    else:
                        color, text = (0, 200, 255), f'{student_name} - verifying...'
                else:
                    color, text = (0, 0, 255), 'Unknown'

                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 3)
                cv2.putText(frame, text, (x, y-12),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
                cv2.putText(frame, f'match {score:.2f} (needs {confidence_threshold})',
                           (x, y+h+28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # A student's streak resets as soon as they leave the frame or stop matching
            self.streaks = {k: v for k, v in self.streaks.items() if k in seen}

            if self.pending:
                msg = f'{self.pending[2]}: PLACE FINGER ON SCANNER'
                (tw, _), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_DUPLEX, 1.0, 2)
                cx = (frame.shape[1] - tw) // 2
                cv2.rectangle(frame, (cx - 20, frame.shape[0] - 110), (cx + tw + 20, frame.shape[0] - 55),
                              (120, 80, 0), -1)
                cv2.putText(frame, msg, (cx, frame.shape[0] - 72), cv2.FONT_HERSHEY_DUPLEX, 1.0,
                            (255, 255, 255), 2)

            now = datetime.now(self.timezone)
            cv2.putText(frame, 'ATTENDANCE SYSTEM', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(frame, f'Date: {now:%d-%m-%Y}', (frame.shape[1]-300, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(frame, f'Time: {now:%I:%M %p}', (frame.shape[1]-300, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            # Names marked this session, newest last, so the queue can keep moving
            for i, data in enumerate(list(self.marked_today.values())[-8:]):
                cv2.putText(frame, f"{data['name']}  {data['time']}", (10, 70 + i * 28),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

            msg, bg, when = self.banner
            if msg and time.time() - when < 2.5:
                (tw, _), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_DUPLEX, 1.1, 2)
                cx, cy = (frame.shape[1] - tw) // 2, frame.shape[0] // 2
                cv2.rectangle(frame, (cx - 20, cy - 45), (cx + tw + 20, cy + 20), bg, -1)
                cv2.putText(frame, msg, (cx, cy), cv2.FONT_HERSHEY_DUPLEX, 1.1, (255, 255, 255), 2)

            cv2.putText(frame, f'Marked Today: {len(self.marked_today)}',
                       (10, frame.shape[0]-20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, 'Press q to quit',
                       (frame.shape[1]-200, frame.shape[0]-20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

            cv2.imshow(window, frame)

            # Stop on 'q' / Esc, or when the window's close button is used - otherwise the
            # camera would keep running in the background with no window
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27) or face_utils.window_closed(window):
                print(f"\n👋 Closing attendance system...")
                break

        camera.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        face_utils.focus_terminal()
        self.finger_pool.shutdown(wait=False, cancel_futures=True)
        self.pool.shutdown(wait=True)      # finish pending Firebase saves

        print(f"\n{'='*70}")
        print(f"ATTENDANCE SESSION SUMMARY")
        print(f"{'='*70}")
        print(f"Total students marked: {len(self.marked_today)}")
        if len(self.marked_today) > 0:
            print(f"\nMarked students:")
            for student_id, data in self.marked_today.items():
                print(f"  ✓ {data['name']} (ID: {student_id}) at {data['time']}")
        print(f"{'='*70}\n")

def main():
    marker = AttendanceMarker()

    if len(marker.student_labels) == 0:
        print("📌 Register students (01_face_registration.py), then train (02_train_model.py)")
        return

    marker.start_recognition()

if __name__ == '__main__':
    main()
