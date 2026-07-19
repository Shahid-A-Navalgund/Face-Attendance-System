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
import config

class FaceRegistration:
    def __init__(self):
        """Initialize face registration system"""
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
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
        
        if self.face_cascade.empty():
            print("❌ Error loading face cascade classifier!")
    
    def save_student_to_firebase(self, student_id, student_name):
        """Save student info to Firebase"""
        try:
            firebase_admin.get_app()
            ref = db.reference(f'students/{student_id}')
            ref.set({
                'name': student_name,
                'student_id': student_id,
                'department': 'CSE',
                'registered_date': datetime.now().strftime('%d-%m-%Y %H:%M:%S')
            })
            print(f"✅ Student saved to Firebase: {student_name}")
        except Exception as e:
            print(f"⚠️ Could not save to Firebase: {e}")

    def capture_faces(self, student_id, student_name, num_images=30):
        """
        Capture multiple face images for a student
        """
        
        # Create directory for student
        student_dir = f'dataset/student_{student_id}_{student_name}'
        if not os.path.exists(student_dir):
            os.makedirs(student_dir)
            print(f"📁 Created directory: {student_dir}")
        
        # Initialize camera
        self.camera = cv2.VideoCapture(0)
        
        if not self.camera.isOpened():
            print("❌ Cannot open camera!")
            return False
        
        print(f"\n{'='*60}")
        print(f"📸 FACE REGISTRATION SYSTEM")
        print(f"{'='*60}")
        print(f"Student Name: {student_name}")
        print(f"Student ID: {student_id}")
        print(f"Images to capture: {num_images}")
        print(f"{'='*60}")
        print(f"\n📌 INSTRUCTIONS:")
        print(f"  1. Position your face in the center of the frame")
        print(f"  2. Look directly at the camera")
        print(f"  3. Vary your angles slightly (left, right, up, down)")
        print(f"  4. Press 'q' to quit early")
        print(f"  5. Ensure good lighting")
        print(f"\n{'='*60}\n")
        
        captured_count = 0
        
        while captured_count < num_images:
            ret, frame = self.camera.read()
            
            if not ret:
                print("❌ Failed to read frame from camera!")
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
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                
                face_roi = gray[y:y+h, x:x+w]
                face_roi = cv2.resize(face_roi, (200, 200))
                
                filename = f'{student_dir}/{student_id}_{captured_count}.jpg'
                cv2.imwrite(filename, face_roi)
                captured_count += 1
                
                time.sleep(0.3)
            
            cv2.putText(frame, f'Captured: {captured_count}/{num_images}', 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            if len(faces) == 0:
                cv2.putText(frame, 'No face detected - Position correctly!', 
                           (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            cv2.putText(frame, 'Press q to quit', 
                       (10, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, (255, 255, 255), 1)
            
            cv2.imshow(f'Face Registration - {student_name}', frame)
            
            key = cv2.waitKey(100)
            if key == ord('q'):
                print("\n⛔ Registration cancelled by user")
                break
        
        self.camera.release()
        cv2.destroyAllWindows()
        
        print(f"\n{'='*60}")
        if captured_count >= 10:
            print(f"✅ SUCCESS! Captured {captured_count} images")
            print(f"   Saved in: {student_dir}")
            # Save to Firebase
            self.save_student_to_firebase(student_id, student_name)
            return True
        else:
            print(f"❌ Only captured {captured_count} images. Need at least 10!")
            return False

def main():
    """Main function for face registration"""
    
    print("\n" + "="*60)
    print("👤 FACE REGISTRATION SYSTEM")
    print("="*60)
    
    registrar = FaceRegistration()
    
    while True:
        student_id = input("\nEnter Student ID/USN (or 'q' to quit): ").strip()
        if student_id.lower() == 'q':
            print("👋 Exiting...")
            break
        
        student_name = input("Enter Student Name: ").strip()
        
        if not student_id or not student_name:
            print("❌ Student ID and Name are required!")
            continue
        
        try:
            num_images = int(input("Number of images to capture (default 30): ") or "30")
        except:
            num_images = 30
        
        success = registrar.capture_faces(student_id, student_name, num_images)
        
        if success:
            print("\n🎉 Registration completed successfully!")
            print("📌 Next: Train the model using 02_train_model.py")
        else:
            print("\n❌ Registration failed or incomplete!")
        
        cont = input("\nRegister another student? (y/n): ").lower()
        if cont != 'y':
            break
    
    print("\n👋 Thank you for using Face Registration System!")

if __name__ == '__main__':
    main()