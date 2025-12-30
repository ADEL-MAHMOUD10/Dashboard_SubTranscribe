# SubTranscribe

This project is a web application built with Flask that allows users to upload audio or video files through a user-friendly interface. The site incorporates HTML, CSS, JavaScript, and Python to create a responsive design and interactive user experience. After uploading a file, users will receive a Subtitle file of the uploaded content.

## Features

- **Modern Dashboard Interface**: User-friendly dashboard to manage all your transcriptions
- **File Upload**: Upload audio or video files through an intuitive drag-and-drop interface
- **URL Processing**: Transcribe content directly from YouTube, Vimeo, or other media links
- **Transcription**: Convert speech in audio/video to accurate text transcriptions
- **Subtitle Generation**: Generate subtitle files in multiple formats
- **Subtitle Format**: Choose between **`SRT`** or **`VTT`** formats for your subtitle files
- **Real-Time Progress Tracking**: Monitor transcription progress with detailed status updates
- **User Accounts**: Create accounts to save and manage your transcription history
- **Customizable Settings**: Personalize your experience through the settings page
- **File Management**: Easily view, download, and delete your transcription files
- **Background Processing**: Heavy tasks are processed in the background using Redis & RQ
- **Docker Support**: Fully containerized application for easy deployment
- **Responsive Design**: Works seamlessly across desktop, tablet, and mobile devices

## Pages

- **Home/Landing Page**: Introduction to the service with main features
- **Dashboard**: View and manage all your transcribed files
- **Transcribe**: Upload new files or provide URLs for transcription
- **Settings**: Customize your account preferences
- **Subtitle Viewer**: View and edit generated subtitles

## How It Works

1. **Upload**: Upload audio/video files through the transcribe page or provide a URL
2. **Processing**: The system processes the media and extracts the speech content
3. **Transcription**: Advanced algorithms convert speech to text with high accuracy
4. **Management**: Access your transcriptions through the dashboard interface
5. **Download**: Download your transcription in various formats (text, SRT, VTT)

## Technologies Used

- **Backend**: Flask (Python web framework)
- **Frontend**: HTML5, CSS3, JavaScript, Bootstrap 5
- **Database**: MongoDB for data storage
- **UI Elements**: AOS for scroll animations, Font Awesome for icons
- **AJAX**: Asynchronous file uploading with progress tracking

## Prerequisites
- Python 3.9 or higher
- Flask 2.0 or higher
- MongoDB
- Redis (for background tasks , ratelimiting and caching)
- AssemblyAI API Key
- **Optional**: Docker & Docker Compose (for containerized deployment)

## Installation

### Method 1: Docker (Recommended)

1. Clone this repository:
   ```bash
   git clone https://github.com/ADEL-MAHMOUD10/SubTranscribe-2.git
   cd SubTranscribe-2
   ```

2. Create a `.env` file based on your configuration (see `.env.example` if available, or populate required keys like `ASSEMBLYAI_KEY`).

3. Run with Docker Compose:
   ```bash
   docker-compose up --build
   ```
   This will start the Flask App, Redis, Nginx, and the RQ Worker automatically.

4. Open your web browser and go to:
   ```
   http://localhost:80
   ```
   (Or port 443 if SSL is configured).

### Method 2: Manual Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/ADEL-MAHMOUD10/SubTranscribe-2.git
   ```
2. Install the required dependencies:

    ```
    pip install -r requirements.txt
    ```

3. Navigate to the project directory and set up a virtual environment:
   ```bash
   cd project_directory
   python -m venv venv
   ```

4. Activate the virtual environment:
   ```bash
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

6. Start the Redis Server (ensure it's running on default port 6379).

7. Start the RQ Worker (in a separate terminal):
   ```bash
   python worker.py
   ```

8. Run the Flask app:
   ```bash
   python app.py
   ```

9. Open your web browser and go to:
   ```
   http://127.0.0.1:5000
   ```

## Project Structure

```
SubTranscribe/
├── app.py              # Main application file
├── worker.py           # Background worker script
├── docker-compose.yml  # Docker orchestration
├── Dockerfile          # Container definition
├── module/             # Application modules
│   ├── auth.py         # Authentication functions
│   ├── config.py       # Configuration settings
│   ├── setting.py      # User settings
│   ├── subtitle.py     # Subtitle generation
│   ├── transcribe.py   # Transcription logic
│   └── reset_pass.py   # Password reset
├── static/             # Static assets
│   ├── css/            # CSS files
│   ├── js/             # JavaScript files
│   └── image/          # Images
└── templates/          # HTML templates
    ├── dashboard.html  # Dashboard page
    ├── settings.html   # Settings page
    ├── transcribe.html # Transcribe page
    ├── job_status.html # Job progress page
    └── ...
```

## Demo

A live demo of this site can be found [here](https://subtranscribe.koyeb.app/).

## Troubleshooting
- If you encounter any issues, ensure that your Python environment is set up correctly with the required libraries.
- Make sure MongoDB is properly installed and running
- Check that all required packages from `requirements.txt` are installed

## License

This project is licensed under the MIT License.

![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg)
![GitHub stars](https://img.shields.io/github/stars/ADEL-MAHMOUD10/SubTranscribe.svg)
