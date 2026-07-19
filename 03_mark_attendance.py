"""
MODULE 3: ATTENDANCE MARKING SYSTEM
Real-time face recognition and attendance marking
"""

import cv2
import os
from datetime import datetime
import pytz
import firebase_admin
from firebase_admin import credentials, db
import config

class AttendanceMarker:
    def __init__(self, model_path='trained_model/face_recognizer.yml'):
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self.model_path = model_path
        self.student_labels = {}
        self.marked_today = {}
        self.timezone = pytz.timezone('Asia/Kolkata')
        
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
        
        # Load the trained model
        if os.path.exists(model_path):
            self.recognizer.read(model_path)
            self._load_student_labels()
            print("✅ Face recognition model loaded successfully!")
        else:
            print(f"❌ Model not found at: {model_path}")
            print("📌 Please train the model first using 02_train_model.py")
    
    def _load_student_labels(self):
        """Load student labels from dataset folder"""
        dataset_path = 'dataset'
        label_id = 0
        
        if not os.path.exists(dataset_path):
            print(f"❌ Dataset path not found: {dataset_path}")
            return
        
        student_dirs = sorted([d for d in os.listdir(dataset_path) 
                              if os.path.isdir(os.path.join(dataset_path, d))])
        
        for student_dir in student_dirs:
            parts = student_dir.split('_')
            if len(parts) >= 2:
                student_id = parts[1]
                student_name = '_'.join(parts[2:]) if len(parts) > 2 else "Unknown"
            else:
                student_id = "Unknown"
                student_name = student_dir
            
            self.student_labels[label_id] = {
                'id': student_id,
                'name': student_name
            }
            label_id += 1
        
        print(f"✅ Loaded {len(self.student_labels)} students from dataset")
    
    def check_firebase_connection(self):
        """Check if Firebase is connected"""
        try:
            firebase_admin.get_app()
            return True
        except ValueError:
            return False
    
    def mark_attendance(self, student_id, student_name):
        now = datetime.now(self.timezone)
        date_str = now.strftime('%d-%m-%Y')
        
        if student_id in self.marked_today:
            if self.marked_today[student_id]['date'] == date_str:
                return False
        
        time_str = now.strftime('%I:%M %p')
        
        try:
            firebase_connected = self.check_firebase_connection()
            
            if firebase_connected:
                ref = db.reference(f'attendance/{student_id}/{date_str}')
                if ref.get():
                    return False
                
                ref.set({
                    'name': student_name,
                    'time': time_str,
                    'status': 'Present'
                })
            
            self.marked_today[student_id] = {
                'name': student_name,
                'date': date_str,
                'time': time_str
            }
            
            return True
            
        except Exception as e:
            print(f"⚠️  Error marking attendance: {e}")
            return False
    
    def get_student_info(self, label):
        """Get student info from label ID"""
        return self.student_labels.get(label, {'id': 'Unknown', 'name': 'Unknown'})
    
    def start_recognition(self, confidence_threshold=50):
        if not os.path.exists(self.model_path):
            print("❌ Model not found! Train the model first.")
            return
        
        camera = cv2.VideoCapture(0)
        
        if not camera.isOpened():
            print("❌ Cannot open camera!")
            return
        
        print("\n" + "="*70)
        print("📹 ATTENDANCE MARKING - REAL-TIME FACE RECOGNITION")
        print("="*70)
        print("📌 Instructions:")
        print("   • Position your face in the frame")
        print("   • Hold still for recognition")
        print("   • Attendance will be marked automatically")
        print("   • Press 'q' to quit")
        print("="*70 + "\n")
        
        while True:
            ret, frame = camera.read()
            
            if not ret:
                print("❌ Cannot read frame from camera!")
                break
            
            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.3,
                minNeighbors=5,
                minSize=(30, 30)
            )
            
            for (x, y, w, h) in faces:
                face_roi = gray[y:y+h, x:x+w]
                face_roi = cv2.resize(face_roi, (200, 200))
                
                label, confidence = self.recognizer.predict(face_roi)
                
                student_info = self.student_labels.get(label, {})
                student_id = student_info.get('id', 'Unknown')
                student_name = student_info.get('name', 'Unknown')
                
                is_recognized = confidence < confidence_threshold
                
                if is_recognized:
                    color = (0, 255, 0)
                    text = f'{student_name} ({confidence:.1f}%)'
                    
                    if self.mark_attendance(student_id, student_name):
                        print(f"✅ MARKED: {student_name} (ID: {student_id}) at {datetime.now(self.timezone).strftime('%I:%M %p')}")
                else:
                    color = (0, 0, 255)
                    text = f'Unknown ({confidence:.1f}%)'
                
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                cv2.putText(frame, text, (x, y-10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                cv2.putText(frame, f'Confidence: {confidence:.1f}%', (x, y+h+25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            now = datetime.now(self.timezone)
            date_str = now.strftime('%d-%m-%Y')
            time_str = now.strftime('%I:%M %p')
            
            cv2.putText(frame, 'ATTENDANCE SYSTEM', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(frame, f'Date: {date_str}', (frame.shape[1]-300, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(frame, f'Time: {time_str}', (frame.shape[1]-300, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(frame, f'Marked Today: {len(self.marked_today)}',
                       (10, frame.shape[0]-20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, 'Press q to quit',
                       (frame.shape[1]-200, frame.shape[0]-20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            
            cv2.imshow('Attendance System - Face Recognition', frame)
            
            key = cv2.waitKey(1)
            if key == ord('q'):
                print(f"\n👋 Closing attendance system...")
                break
        
        camera.release()
        cv2.destroyAllWindows()
        
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
    marker = AttendanceMarker('trained_model/face_recognizer.yml')
    
    if len(marker.student_labels) == 0:
        print("❌ No students found in dataset!")
        print("📌 Please register students first using 01_face_registration.py")
        return
    
    marker.start_recognition(confidence_threshold=50)

if __name__ == '__main__':
    main()