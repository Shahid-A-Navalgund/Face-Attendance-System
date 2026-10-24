"""
MODULE 1: FACE REGISTRATION SYSTEM
Capture and store student face images
"""

import cv2
import os
import time
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
import re
import shutil
import pytz
import config
import face_utils
import fingerprint

class FaceRegistration:
    def __init__(self):
        """Initialize face registration system"""
        self.engine = face_utils.FaceEngine()
        self.camera = None
        
        # Initialize Firebase
        try:
            firebase_admin.get_app()
        except ValueError:
            try:
                cred = credentials.Certificate(config.SERVICE_ACCOUNT_KEY)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': config.FIREBASE_DATABASE_URL
                })
                print("✅ Firebase connected successfully!")
            except Exception as e:
                print(f"⚠️ Firebase error: {e}")

    
    def save_student_to_firebase(self, student_id, student_name, department):
        """Save student info to Firebase"""
        try:
            firebase_admin.get_app()
            ref = db.reference(f'students/{student_id}')
            ref.set({
                'name': student_name,
                'student_id': student_id,
                'department': department,
                'registered_date': datetime.now().strftime('%d-%m-%Y %H:%M:%S')
            })
            print(f"✅ Student saved to Firebase: {student_name}")
        except Exception as e:
            print(f"⚠️ Could not save to Firebase: {e}")

    # (on-screen instruction, photos to take) - distinct angles beat many near-identical shots
    POSES = [
        ('LOOK STRAIGHT', 5),
        ('TURN SLIGHTLY LEFT', 4),
        ('TURN SLIGHTLY RIGHT', 4),
        ('TILT CHIN UP', 3),
        ('TILT CHIN DOWN', 3),
    ]
    GET_READY_SECONDS = 2     # countdown before each pose
    SHOT_INTERVAL = 0.25      # seconds between photos within a pose

    def _largest_face(self, frame):
        faces = self.engine.detect(frame)
        return faces[0] if faces else None

    @staticmethod
    def _banner(frame, text, sub=None):
        """Big instruction text on a dark strip at the top of the frame."""
        width = frame.shape[1]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (width, 120 if sub else 90), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 1.6, 3)
        cv2.putText(frame, text, ((width - tw) // 2, 62), cv2.FONT_HERSHEY_DUPLEX,
                    1.6, (0, 255, 255), 3)
        if sub:
            (sw, _), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            cv2.putText(frame, sub, ((width - sw) // 2, 102), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (255, 255, 255), 2)

    def capture_faces(self, student_id, student_name, department):
        """
        Guided capture: walks the student through each pose in POSES,
        showing the instruction on screen and auto-taking the photos.
        """

        student_dir = f'dataset/student_{student_id}_{student_name}'
        os.makedirs(student_dir, exist_ok=True)

        self.camera = face_utils.open_camera()
        if not self.camera.isOpened():
            print("❌ Cannot open camera!")
            print("📌 macOS: System Settings → Privacy & Security → Camera → allow your terminal/VS Code")
            self._remove_if_empty(student_dir)
            return False

        total = sum(n for _, n in self.POSES)
        print(f"\n{'='*60}")
        print(f"📸 FACE REGISTRATION: {student_name} ({student_id})")
        print(f"{'='*60}")
        print("Follow the instruction shown on the camera window.")
        print(f"{len(self.POSES)} poses, {total} photos, about 15 seconds. Press 'q' to cancel.")
        print(f"{'='*60}\n")

        window = f'Face Registration - {student_name}'
        captured = 0
        pose_idx, pose_shots = 0, 0
        pose_start = time.time()
        last_shot = 0.0
        failed_reads = 0

        while pose_idx < len(self.POSES):
            ret, frame = self.camera.read()
            if not ret:
                failed_reads += 1          # camera may need a moment to warm up
                if failed_reads > 50:
                    print("❌ Failed to read frame from camera!")
                    break
                cv2.waitKey(20)
                continue
            failed_reads = 0

            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face = self._largest_face(frame)
            instruction, shots_needed = self.POSES[pose_idx]
            now = time.time()
            countdown = self.GET_READY_SECONDS - (now - pose_start)

            if face is not None:
                x, y, w, h = face[:4].astype(int)
                color = (0, 255, 0) if countdown <= 0 else (0, 200, 255)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)

            step = f'Step {pose_idx + 1} of {len(self.POSES)}'
            if countdown > 0:
                self._banner(frame, instruction, f'{step}  -  get ready... {int(countdown) + 1}')
            else:
                self._banner(frame, instruction, f'{step}  -  photo {pose_shots}/{shots_needed}')
                if face is not None and now - last_shot >= self.SHOT_INTERVAL:
                    face_img = face_utils.face_crop(gray, face)
                    cv2.imwrite(f'{student_dir}/{student_id}_{captured}.jpg', face_img)
                    captured += 1
                    pose_shots += 1
                    last_shot = now
                    if pose_shots >= shots_needed:
                        pose_idx, pose_shots = pose_idx + 1, 0
                        pose_start = now

            if face is None:
                cv2.putText(frame, 'No face detected - move into the frame',
                            (20, frame.shape[0] - 60), cv2.FONT_HERSHEY_SIMPLEX,
                            0.9, (0, 0, 255), 2)

            # Overall progress bar
            h_img, w_img = frame.shape[:2]
            cv2.rectangle(frame, (0, h_img - 14), (w_img, h_img), (60, 60, 60), -1)
            cv2.rectangle(frame, (0, h_img - 14), (int(w_img * captured / total), h_img),
                          (0, 255, 0), -1)
            cv2.putText(frame, f'{captured}/{total}   q = cancel', (20, h_img - 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            cv2.imshow(window, frame)
            # 'q' / Esc or the window's close button cancels and turns the camera off
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27) or face_utils.window_closed(window):
                print("\n⛔ Registration cancelled by user")
                break

        self.camera.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        face_utils.focus_terminal()

        print(f"\n{'='*60}")
        if captured >= 10:
            self._remove_stale_images(student_dir, student_id, captured)
            print(f"✅ SUCCESS! Captured {captured} images")
            print(f"   Saved in: {student_dir}")
            self._remove_other_folders(student_id, student_dir)
            self.save_student_to_firebase(student_id, student_name, department)
            return True
        print(f"❌ Only captured {captured} images. Need at least 10!")
        self._remove_if_empty(student_dir)
        return False

    @staticmethod
    def _remove_stale_images(student_dir, student_id, count):
        """Re-registration: drop leftover images from an older, longer capture."""
        for f in os.listdir(student_dir):
            stem = os.path.splitext(f)[0].upper()
            prefix = f'{student_id}_'
            if stem.startswith(prefix) and stem[len(prefix):].isdigit() and int(stem[len(prefix):]) >= count:
                os.remove(os.path.join(student_dir, f))

    @staticmethod
    def _remove_other_folders(student_id, keep_dir):
        """One folder per ID: drop older registrations of the same ID (e.g. a misspelt name)."""
        for d in os.listdir('dataset'):
            path = os.path.join('dataset', d)
            parts = d.split('_')
            if (len(parts) > 1 and parts[1].upper() == student_id and os.path.isdir(path)
                    and not os.path.samefile(path, keep_dir)):
                shutil.rmtree(path)
                print(f"🗑️  Removed older registration folder: {d}")

    @staticmethod
    def mark_attendance(student_id, student_name):
        """The student was just seen on camera, so mark them present for today."""
        try:
            earlier = face_utils.mark_present(student_id, student_name,
                                              datetime.now(pytz.timezone('Asia/Kolkata')))
            if earlier:
                print(f"ℹ️  {student_name} was already marked present today at {earlier}")
            else:
                print(f"✅ Attendance marked: {student_name} (ID: {student_id})")
        except Exception as e:
            print(f"⚠️ Could not mark attendance: {e}")

    @staticmethod
    def existing_folder(student_id):
        """(folder path, name) of an already-registered student, or (None, None)."""
        if os.path.isdir('dataset'):
            for d in os.listdir('dataset'):
                parts = d.split('_')
                if len(parts) > 2 and parts[1].upper() == student_id:
                    return os.path.join('dataset', d), '_'.join(parts[2:]).upper()
        return None, None

    def enroll_fingerprint(self, student_id, student_name, student_dir):
        """Scan the same finger twice; save it only if both scans agree and no other
        student already owns this fingerprint."""
        print(f"\n{'='*60}")
        print(f"🖐️  FINGERPRINT REGISTRATION: {student_name} ({student_id})")
        print(f"{'='*60}")
        while True:
            try:
                print("👉 Place a finger (e.g. right thumb) flat on the scanner...")
                first = fingerprint.capture()
                print("✅ Scan 1 done. Lift the finger, then place the SAME finger again...")
                second = fingerprint.capture()
                if not fingerprint.verify(second, first):
                    print("❌ The two scans did not match - use the same finger, pressed flat")
                else:
                    owner = next((sid for sid, t in fingerprint.load_templates().items()
                                  if sid != student_id and fingerprint.verify(first, t)), None)
                    if owner:
                        print(f"❌ This fingerprint is already registered to student {owner}")
                    else:
                        fingerprint.save_template(student_dir, first)
                        try:
                            db.reference(f'students/{student_id}').update({'fingerprint': True})
                        except Exception as e:
                            print(f"⚠️ Could not update Firebase: {e}")
                        print("✅ Fingerprint registered")
                        return True
            except fingerprint.FingerprintError as e:
                print(f"❌ {e}")
            if input("Press Enter to try again, or 's' to skip: ").strip().lower() == 's':
                print("⚠️  No fingerprint saved - this student cannot mark attendance until one is added")
                print("   (run this script again with the same ID and choose 'f')")
                return False

    @staticmethod
    def _remove_if_empty(student_dir):
        if os.path.isdir(student_dir) and not os.listdir(student_dir):
            os.rmdir(student_dir)


def main():
    """Main function for face registration"""
    
    print("\n" + "="*60)
    print("👤 FACE REGISTRATION SYSTEM")
    print("="*60)
    
    registrar = FaceRegistration()
    if fingerprint.enabled() and not fingerprint.wait_for_device():
        return
    
    while True:
        print("\n" + "-"*60)
        print("👤 NEW STUDENT")
        print("-"*60)
        student_id = input("Enter Student ID/USN (or 'q' to quit): ").strip()
        if student_id.lower() == 'q':
            print("👋 Exiting...")
            break
        student_id = student_id.upper()

        existing_dir, existing_name = registrar.existing_folder(student_id)
        if existing_dir and fingerprint.enabled():
            choice = input(f"{student_id} ({existing_name}) is already registered. "
                           "[f] add/replace fingerprint only, [r] register again, "
                           "Enter = cancel: ").strip().lower()
            if choice == 'f':
                registrar.enroll_fingerprint(student_id, existing_name, existing_dir)
                continue
            if choice != 'r':
                continue
        
        student_name = input("Enter Student Name: ").strip()
        department = input("Enter Department (e.g. CSE, ECE, MECH): ").strip().upper()
        student_id, student_name = face_utils.normalize(student_id, student_name)
        
        if not student_id or not student_name or not department:
            print("❌ Student ID, Name and Department are required!")
            continue
        # IDs/names become folder names, so reject pasted commands and paths
        if not re.fullmatch(r'[A-Za-z0-9]+', student_id):
            print("❌ Student ID must be letters and digits only (e.g. 20231CIT0122)")
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", student_name):
            print("❌ Name must contain letters, spaces, dots or hyphens only")
            continue
        if not re.fullmatch(r'[A-Z0-9 &-]+', department):
            print("❌ Department must be letters/digits only (e.g. CSE)")
            continue
        
        success = registrar.capture_faces(student_id, student_name, department)
        
        if success:
            finger_ok = True
            if fingerprint.enabled():
                finger_ok = registrar.enroll_fingerprint(
                    student_id, student_name, f'dataset/student_{student_id}_{student_name}')
            # Retrain right away so the new student is recognised by 03_mark_attendance.py
            face_utils.retrain()
            if finger_ok:
                registrar.mark_attendance(student_id, student_name)
            print("\n🎉 Registration completed successfully!" if finger_ok
                  else "\n⚠️  Face registered, fingerprint missing")
            print("📌 Enter the next student's ID to add more students, or 'q' to finish")
        else:
            print("\n❌ Registration failed or incomplete!")
    
    print("\n👋 Thank you for using Face Registration System!")

if __name__ == '__main__':
    main()