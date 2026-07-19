"""
MODULE 4: ADMIN DASHBOARD
GUI for managing students and viewing attendance reports
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import firebase_admin
from firebase_admin import credentials, db
import pandas as pd
from datetime import datetime
import pytz
import config

class AdminDashboard:
    def __init__(self, root):
        """Initialize admin dashboard"""
        self.root = root
        self.root.title("📊 Attendance System - Admin Dashboard")
        self.root.geometry("1000x700")
        self.root.configure(bg='#ecf0f1')
        
        # Try to initialize Firebase
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
            except Exception as e:
                self.firebase_ready = False
                messagebox.showwarning("Warning", 
                    f"Firebase not initialized!\n{e}")
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the user interface"""
        
        # Header
        header = tk.Frame(self.root, bg='#2c3e50', height=70)
        header.pack(fill='x')
        
        title = tk.Label(header, text='📊 ATTENDANCE MANAGEMENT SYSTEM',
                        font=('Arial', 18, 'bold'), fg='white', bg='#2c3e50')
        title.pack(pady=15)
        
        # Notebook (tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Tab 1: Dashboard
        self.dashboard_tab = tk.Frame(self.notebook)
        self.notebook.add(self.dashboard_tab, text='📈 Dashboard')
        self.setup_dashboard_tab()
        
        # Tab 2: Students
        self.students_tab = tk.Frame(self.notebook)
        self.notebook.add(self.students_tab, text='👥 Students')
        self.setup_students_tab()
        
        # Tab 3: Reports
        self.reports_tab = tk.Frame(self.notebook)
        self.notebook.add(self.reports_tab, text='📄 Reports')
        self.setup_reports_tab()
        
        # Tab 4: Settings
        self.settings_tab = tk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text='⚙️ Settings')
        self.setup_settings_tab()
    
    def setup_dashboard_tab(self):
        """Dashboard tab with statistics"""
        
        frame = ttk.Frame(self.dashboard_tab, padding="20")
        frame.pack(fill='both', expand=True)
        
        # Refresh button
        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill='x', pady=10)
        
        ttk.Button(btn_frame, text='🔄 Refresh Statistics',
                  command=self.refresh_dashboard).pack(side='left', padx=5)
        
        # Info display area
        self.info_text = tk.Text(frame, height=25, width=100, 
                                bg='white', relief='sunken')
        self.info_text.pack(fill='both', expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.info_text)
        scrollbar.pack(side='right', fill='y')
        self.info_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.info_text.yview)
        
        # Load initial data
        self.refresh_dashboard()
    
    def refresh_dashboard(self):
        """Refresh dashboard statistics"""
        
        self.info_text.delete('1.0', 'end')
        
        info = "🔄 Loading statistics...\n"
        self.info_text.insert('1.0', info)
        self.root.update()
        
        try:
            if not self.firebase_ready:
                self.info_text.insert('end', "❌ Firebase not connected!\n")
                return
            
            # Get total students
            students_ref = db.reference('students')
            students_data = students_ref.get()
            total_students = len(students_data) if students_data else 0
            
            # Get today's attendance
            ist = pytz.timezone('Asia/Kolkata')
            today = datetime.now(ist).strftime('%d-%m-%Y')
            attendance_ref = db.reference('attendance')
            attendance_data = attendance_ref.get()
            
            present_today = 0
            if attendance_data:
                for student_id, dates in attendance_data.items():
                    if today in dates:
                        present_today += 1
            
            absent_today = total_students - present_today
            attendance_rate = (present_today/total_students*100) if total_students > 0 else 0
            
            # Create formatted output
            info = f"""
{'='*60}
ATTENDANCE SYSTEM - DASHBOARD STATISTICS
{'='*60}

📊 SUMMARY
  • Total Registered Students: {total_students}
  • Present Today ({today}): {present_today}
  • Absent Today: {absent_today}
  • Attendance Rate: {attendance_rate:.1f}%

{'='*60}
📅 TODAY'S ATTENDANCE ({today})
{'='*60}
"""
            
            if attendance_data and today:
                count = 0
                for student_id, dates in sorted(attendance_data.items()):
                    if today in dates:
                        count += 1
                        attendance = dates[today]
                        info += f"\n{count}. {attendance.get('name', 'N/A'):30} "
                        info += f"(ID: {student_id:10}) "
                        info += f"Time: {attendance.get('time', 'N/A')}"
            else:
                info += "\n  (No attendance marked yet today)\n"
            
            info += f"\n{'='*60}"
            info += f"\nLast Updated: {datetime.now(ist).strftime('%d-%m-%Y %H:%M:%S')}\n"
            info += f"{'='*60}\n"
            
            self.info_text.delete('1.0', 'end')
            self.info_text.insert('1.0', info)
            
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}\n\nPlease check Firebase connection."
            self.info_text.delete('1.0', 'end')
            self.info_text.insert('1.0', error_msg)
    
    def setup_students_tab(self):
        """Students management tab"""
        
        frame = ttk.Frame(self.students_tab, padding="20")
        frame.pack(fill='both', expand=True)
        
        # Search frame
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill='x', pady=10)
        
        ttk.Label(search_frame, text='Search Student:').pack(side='left', padx=5)
        self.search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_var,
                 width=30).pack(side='left', padx=5)
        
        ttk.Button(search_frame, text='Search',
                  command=self.search_students).pack(side='left', padx=5)
        ttk.Button(search_frame, text='Reload All',
                  command=self.load_students_list).pack(side='left', padx=5)
        
        # Treeview frame
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill='both', expand=True, pady=10)
        
        # Create treeview
        columns = ('ID', 'Name', 'Department', 'Registered')
        self.students_tree = ttk.Treeview(tree_frame, columns=columns, height=20)
        self.students_tree.column('#0', width=0, stretch='no')
        self.students_tree.column('ID', width=80, anchor='center')
        self.students_tree.column('Name', width=200)
        self.students_tree.column('Department', width=100)
        self.students_tree.column('Registered', width=150)
        
        for col in columns:
            self.students_tree.heading(col, text=col)
        
        self.students_tree.pack(fill='both', expand=True, side='left')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical',
                                 command=self.students_tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.students_tree.configure(yscroll=scrollbar.set)
        
        # Buttons frame
        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill='x', pady=10)
        
        ttk.Button(btn_frame, text='🗑️ Delete Selected',
                  command=self.delete_student).pack(side='left', padx=5)
        ttk.Button(btn_frame, text='👁️ View Attendance',
                  command=self.view_student_attendance).pack(side='left', padx=5)
        
        # Load students
        self.load_students_list()
    
    def load_students_list(self):
        """Load and display all students"""
        
        for item in self.students_tree.get_children():
            self.students_tree.delete(item)
        
        try:
            if not self.firebase_ready:
                return
            
            ref = db.reference('students')
            data = ref.get()
            
            if data:
                for student_id, student_info in sorted(data.items()):
                    values = (
                        student_id,
                        student_info.get('name', 'N/A'),
                        student_info.get('department', 'N/A'),
                        student_info.get('registered_date', 'N/A')[:10]
                    )
                    self.students_tree.insert('', 'end', values=values)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error loading students: {e}")
    
    def search_students(self):
        """Search students by name or ID"""
        
        search_term = self.search_var.get().lower()
        
        for item in self.students_tree.get_children():
            self.students_tree.delete(item)
        
        try:
            if not self.firebase_ready:
                return
            
            ref = db.reference('students')
            data = ref.get()
            
            if data:
                for student_id, student_info in data.items():
                    if (search_term in student_id.lower() or 
                        search_term in student_info.get('name', '').lower()):
                        
                        values = (
                            student_id,
                            student_info.get('name', 'N/A'),
                            student_info.get('department', 'N/A'),
                            student_info.get('registered_date', 'N/A')[:10]
                        )
                        self.students_tree.insert('', 'end', values=values)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error searching: {e}")
    
    def delete_student(self):
        """Delete selected student"""
        
        selection = self.students_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a student!")
            return
        
        item = selection[0]
        student_id = self.students_tree.item(item, 'values')[0]
        student_name = self.students_tree.item(item, 'values')[1]
        
        if messagebox.askyesno("Confirm Delete", 
                              f"Delete student {student_name} ({student_id})?\n\nThis cannot be undone!"):
            try:
                if self.firebase_ready:
                    ref = db.reference(f'students/{student_id}')
                    ref.delete()
                
                messagebox.showinfo("Success", f"Student {student_name} deleted!")
                self.load_students_list()
                
            except Exception as e:
                messagebox.showerror("Error", f"Error deleting: {e}")
    
    def view_student_attendance(self):
        """View attendance for selected student"""
        
        selection = self.students_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a student!")
            return
        
        item = selection[0]
        student_id = self.students_tree.item(item, 'values')[0]
        student_name = self.students_tree.item(item, 'values')[1]
        
        try:
            if not self.firebase_ready:
                return
            
            ref = db.reference(f'attendance/{student_id}')
            data = ref.get()
            
            attendance_info = f"ATTENDANCE - {student_name} (ID: {student_id})\n"
            attendance_info += "="*50 + "\n\n"
            
            if data:
                dates = sorted(data.keys())
                for date in dates:
                    attendance = data[date]
                    attendance_info += f"{date}: {attendance.get('time', 'N/A')} - "
                    attendance_info += f"{attendance.get('status', 'N/A')}\n"
                
                attendance_info += f"\nTotal: {len(dates)} days"
            else:
                attendance_info += "No attendance records found!"
            
            messagebox.showinfo("Attendance", attendance_info)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error: {e}")
    
    def setup_reports_tab(self):
        """Reports generation tab"""
        
        frame = ttk.Frame(self.reports_tab, padding="20")
        frame.pack(fill='both', expand=True)
        
        ttk.Label(frame, text='Report Type:', font=('Arial', 11, 'bold')).pack(pady=10)
        
        self.report_var = tk.StringVar(value='daily')
        ttk.Radiobutton(frame, text='Daily Report (Today)',
                       variable=self.report_var,
                       value='daily').pack()
        ttk.Radiobutton(frame, text='Monthly Report',
                       variable=self.report_var,
                       value='monthly').pack()
        ttk.Radiobutton(frame, text='Student Attendance Summary',
                       variable=self.report_var,
                       value='student').pack()
        
        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text='📊 Generate Report',
                  command=self.generate_report).pack(side='left', padx=5)
        ttk.Button(btn_frame, text='💾 Export as Excel',
                  command=self.export_report).pack(side='left', padx=5)
        
        ttk.Label(frame, text='Report Preview:', font=('Arial', 10, 'bold')).pack(pady=10)
        
        self.report_text = tk.Text(frame, height=25, width=100, bg='white')
        self.report_text.pack(fill='both', expand=True)
        
        scrollbar = ttk.Scrollbar(self.report_text)
        scrollbar.pack(side='right', fill='y')
        self.report_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.report_text.yview)
    
    def generate_report(self):
        """Generate attendance report"""
        
        report_type = self.report_var.get()
        
        self.report_text.delete('1.0', 'end')
        self.report_text.insert('1.0', "🔄 Generating report...\n")
        self.root.update()
        
        try:
            if not self.firebase_ready:
                self.report_text.insert('end', "❌ Firebase not connected!")
                return
            
            ref = db.reference('attendance')
            data = ref.get()
            
            if not data:
                self.report_text.delete('1.0', 'end')
                self.report_text.insert('1.0', "❌ No attendance data found!")
                return
            
            ist = pytz.timezone('Asia/Kolkata')
            report_text = ""
            
            if report_type == 'daily':
                today = datetime.now(ist).strftime('%d-%m-%Y')
                report_text = f"{'='*60}\n"
                report_text += f"DAILY ATTENDANCE REPORT\n"
                report_text += f"Date: {today}\n"
                report_text += f"{'='*60}\n\n"
                
                count = 0
                for student_id in sorted(data.keys()):
                    dates = data[student_id]
                    if today in dates:
                        count += 1
                        attendance = dates[today]
                        report_text += f"{count}. {attendance.get('name', 'N/A'):30} "
                        report_text += f"(ID: {student_id:10}) "
                        report_text += f"at {attendance.get('time', 'N/A')}\n"
                
                report_text += f"\n{'='*60}\n"
                report_text += f"Total Present: {count}\n"
                report_text += f"{'='*60}\n"
            
            elif report_type == 'monthly':
                current_month = datetime.now().strftime('%m-%Y')
                report_text = f"{'='*60}\n"
                report_text += f"MONTHLY ATTENDANCE REPORT\n"
                report_text += f"Month: {current_month}\n"
                report_text += f"{'='*60}\n\n"
                
                for student_id in sorted(data.keys()):
                    dates = data[student_id]
                    present_count = sum(1 for date in dates if current_month in date)
                    
                    if present_count > 0:
                        report_text += f"Student ID: {student_id}\n"
                        for date in sorted(dates.keys()):
                            if current_month in date:
                                report_text += f"  ✓ {date}\n"
                        report_text += f"Total: {present_count} days\n\n"
            
            self.report_text.delete('1.0', 'end')
            self.report_text.insert('1.0', report_text)
            
        except Exception as e:
            self.report_text.delete('1.0', 'end')
            self.report_text.insert('1.0', f"❌ Error: {e}")
    
    def export_report(self):
        """Export report as Excel"""
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("CSV files", "*.csv")],
            initialfile=f"attendance_report_{datetime.now().strftime('%d-%m-%Y')}"
        )
        
        if not file_path:
            return
        
        try:
            if not self.firebase_ready:
                messagebox.showerror("Error", "Firebase not connected!")
                return
            
            ref = db.reference('attendance')
            data = ref.get()
            
            if not data:
                messagebox.showwarning("Warning", "No attendance data to export!")
                return
            
            records = []
            for student_id, dates in data.items():
                for date, attendance in dates.items():
                    records.append({
                        'Student ID': student_id,
                        'Name': attendance.get('name', 'N/A'),
                        'Date': date,
                        'Time': attendance.get('time', 'N/A'),
                        'Status': attendance.get('status', 'Present')
                    })
            
            df = pd.DataFrame(records)
            
            if file_path.endswith('.xlsx'):
                df.to_excel(file_path, index=False, sheet_name='Attendance')
            else:
                df.to_csv(file_path, index=False)
            
            messagebox.showinfo("Success", f"Report exported!\n\n{file_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error exporting: {e}")
    
    def setup_settings_tab(self):
        """Settings tab"""
        
        frame = ttk.Frame(self.settings_tab, padding="20")
        frame.pack(fill='both', expand=True)
        
        info = tk.Text(frame, height=20, width=80, bg='white')
        info.pack(fill='both', expand=True)
        
        info_text = """
╔════════════════════════════════════════════════════════════════╗
║           ATTENDANCE SYSTEM - SETTINGS & INFO                  ║
╚════════════════════════════════════════════════════════════════╝

📌 SYSTEM INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Version: 1.0
Technology: OpenCV + Firebase
Model: LBPH (Local Binary Patterns Histograms)
GUI Framework: Tkinter

🎯 FEATURES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Real-time Face Recognition
✓ Cloud-based Attendance Storage
✓ Student Management
✓ Attendance Reports
✓ Excel Export
✓ Dashboard Statistics
✓ Search Functionality

⚡ QUICK TIPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Register students with at least 30 face images
2. Train the model after registering students
3. Use good lighting for accurate face recognition
4. Retrain model if accuracy drops
"""
        
        info.insert('1.0', info_text)
        info.config(state='disabled')

def main():
    """Main function"""
    root = tk.Tk()
    app = AdminDashboard(root)
    root.mainloop()

if __name__ == '__main__':
    main()