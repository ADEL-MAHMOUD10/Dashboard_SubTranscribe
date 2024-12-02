import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox

def convert_video_to_audio():
    # فتح نافذة لاختيار الملف
    video_path = filedialog.askopenfilename(title="Select a Video File", filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov")])
    
    if video_path:
        # تحديد اسم ملف الصوت الناتج
        audio_path = video_path.rsplit('.', 1)[0] + ".mp3"
        
        try:
            # تنفيذ أمر FFmpeg لتحويل الفيديو إلى صوت
            subprocess.run([r"C:\ffmpeg\bin\ffmpeg.exe", "-i", video_path, audio_path], check=True)

            
            messagebox.showinfo("Success", f"File successfully converted to audio: {audio_path}")
        except subprocess.CalledProcessError:
            messagebox.showerror("Error", "Failed to convert the video to audio.")
    else:
        messagebox.showwarning("No file selected", "Please select a video file.")

# إعداد واجهة المستخدم
root = tk.Tk()
root.withdraw()  # إخفاء النافذة الرئيسية (لأننا نحتاج فقط إلى نافذة لاختيار الملف)

# استدعاء الوظيفة لتحويل الفيديو إلى صوت
convert_video_to_audio()
