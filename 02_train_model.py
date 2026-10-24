"""
MODULE 2: FACE RECOGNITION TRAINING
Compute an SFace embedding for every registered photo
"""

import cv2
import os
import numpy as np
import face_utils

class FaceTrainer:
    def __init__(self):
        """Initialize face trainer"""
        self.engine = face_utils.FaceEngine()
        self.current_id = 0
        self.student_labels = {}
    
    def get_images_and_labels(self, dataset_path='dataset'):
        """
        Extract images and labels from dataset folder
        
        Args:
            dataset_path: Path to dataset folder
        
        Returns:
            tuple: (faces list, labels list)
        """
        faces = []
        labels = []
        
        print(f"\n📂 Reading images from: {dataset_path}")
        print("="*60)
        
        if not os.path.exists(dataset_path):
            print(f"❌ Dataset path not found: {dataset_path}")
            return [], []
        
        # Get all student folders (sorted for consistent ID assignment)
        student_dirs = sorted([d for d in os.listdir(dataset_path) 
                              if os.path.isdir(os.path.join(dataset_path, d))])
        
        if not student_dirs:
            print("❌ No student folders found in dataset!")
            return [], []
        
        # Process each student folder
        for student_dir in student_dirs:
            student_path = os.path.join(dataset_path, student_dir)
            
            # Parse student folder name format: student_ID_Name
            parts = student_dir.split('_')
            if len(parts) >= 2:
                student_id = parts[1]
                student_name = '_'.join(parts[2:]) if len(parts) > 2 else "Unknown"
                student_id, student_name = face_utils.normalize(student_id, student_name)
            else:
                student_id = "Unknown"
                student_name = student_dir
            
            # Store label mapping
            self.student_labels[self.current_id] = {
                'id': student_id,
                'name': student_name
            }
            
            print(f"\n📌 Processing: {student_name} (ID: {student_id})")
            
            # Read all images from student folder
            image_files = [f for f in os.listdir(student_path) 
                          if f.endswith(('.jpg', '.jpeg', '.png'))]
            
            image_count = 0
            for image_name in image_files:
                image_path = os.path.join(student_path, image_name)
                
                try:
                    # Read image in grayscale
                    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
                    
                    vec = self.engine.embed_photo(img) if img is not None else None
                    if vec is not None:
                        faces.append(vec)
                        labels.append(self.current_id)
                        image_count += 1
                        
                except Exception as e:
                    print(f"   ⚠️  Error reading {image_name}: {e}")
            
            if image_count > 0:
                print(f"   ✅ Loaded {image_count}/{len(image_files)} images (no face found in the rest)"
                  if image_count < len(image_files) else f"   ✅ Loaded {image_count} images")
                self.current_id += 1
            else:
                print(f"   ⚠️  No valid images found in folder - skipped")
                del self.student_labels[self.current_id]
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"LOADING SUMMARY")
        print(f"{'='*60}")
        print(f"Total students: {self.current_id}")
        print(f"Total images: {len(faces)}")
        print(f"Unique labels: {len(set(labels))}")
        
        return faces, labels
    
    def train_recognizer(self, dataset_path='dataset', 
                        output_path=face_utils.MODEL_PATH):
        """
        Build the face embeddings the attendance system matches against
        
        Args:
            dataset_path: Path to dataset folder
            output_path: Where to save the trained model
        
        Returns:
            bool: True if training successful
        """
        
        print("\n" + "="*60)
        print("🤖 TRAINING FACE RECOGNIZER")
        print("="*60)
        
        # Extract images and labels from dataset
        faces, labels = self.get_images_and_labels(dataset_path)
        
        if len(faces) == 0:
            print("\n❌ Cannot train: No images found in dataset!")
            print("📌 Please register students first using 01_face_registration.py")
            return False
        
        faces = np.array(faces, dtype=np.float32)
        labels = np.array(labels)
        
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save the embeddings plus the label -> student mapping they belong to,
            # so attendance never has to guess the mapping from the dataset folder
            np.savez(output_path, embeddings=faces, labels=labels)
            face_utils.save_labels(self.student_labels)
            
            print(f"\n✅ TRAINING COMPLETED!")
            print(f"{'='*60}")
            print(f"💾 Model saved: {output_path}")
            print(f"📊 Trained on {len(faces)} images from {len(set(labels))} students")
            print(f"{'='*60}")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Training failed: {e}")
            return False
    
    def print_student_mapping(self):
        """Print the student ID to label mapping"""
        print("\n" + "="*60)
        print("STUDENT ID TO LABEL MAPPING")
        print("="*60)
        for label, info in sorted(self.student_labels.items()):
            print(f"Label {label}: {info['name']} (ID: {info['id']})")
        print("="*60)

def main():
    """Main function for training"""
    
    print("\n" + "="*60)
    print("🤖 FACE RECOGNITION MODEL TRAINING")
    print("="*60)
    
    trainer = FaceTrainer()
    
    # Train the model
    success = trainer.train_recognizer(
        dataset_path='dataset',
        output_path=face_utils.MODEL_PATH
    )
    
    if success:
        # Print student mapping
        trainer.print_student_mapping()
        
        print(f"\n🎉 TRAINING SUCCESSFUL!")
        print(f"{'='*60}")
        print(f"📌 Next steps:")
        print(f"   1. Run 03_mark_attendance.py to start marking attendance")
        print(f"   2. Or run 04_admin_dashboard.py to view reports")
        print(f"{'='*60}")
    else:
        print(f"\n❌ TRAINING FAILED!")
        print(f"   Please check the dataset folder and try again")

if __name__ == '__main__':
    main()
