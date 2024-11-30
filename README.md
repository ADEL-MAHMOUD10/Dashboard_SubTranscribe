# SubTranscribe

This project is a web application built with Flask that allows users to upload audio or video files through a user-friendly interface. The site incorporates HTML, CSS, JavaScript, and Python to create a responsive design and interactive user experience. After uploading a file, users will receive a Subtitle file of the uploaded content.

## Features

- **File Upload**: Users can easily upload audio or video files through the web interface.
- **Transcription**: After uploading, users receive a Subtitle file of the uploaded media.
- **Subtitle Format**: Now you can choose between **`SRT`** or **`VTT`** formats for your Subtitle file  
- **Clean and Simple UI**: The website is designed with a minimal and responsive layout for better user interaction.
- **Real-Time File Upload Alerts**: The JavaScript integration notifies users when a file is being uploaded.
- **Alerts**: Users are notified about the upload process with real-time messages.
- **File Management**: Uploaded files are automatically stored in the designated folder on the server.
- **Flask Backend**: A lightweight backend using Flask for handling file uploads, transcriptions, and serving the webpage.

## How It Works

1. **Homepage**: The main page provides a file upload form where users can select and upload audio or video files.
2. **Transcription Process**: Once the file is uploaded, it will be processed, and a Subtitle file will be generated.
3. **File Handling**: The uploaded files are saved in the server's `uploads/` directory, and the Subtitle file is provided to the user for download.

## Technologies Used

- **Flask**: Python-based web framework for backend development.
- **HTML5 & CSS3**: To build the structure and style of the website.
- **JavaScript**: For client-side interactivity and alerts.

## Prerequisites
- Python 3.7 or higher
- Flask 2.0 or higher

## How to Use

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

4. Activate the virtual environment and install dependencies:
   ```bash
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   pip install flask
   ```

4. Run the Flask app:
   ```bash
   python app.py
   ```

5. Open your web browser and go to:
   ```
   http://127.0.0.1:8000
   ```

6. Use the interface to upload files, which will be saved to the server's `uploads/` directory.


## Demo

A live demo of this site can be found [here]().

## Troubleshooting
- If you encounter any issues, ensure that your Python environment is set up correctly with the required libraries.
- make sure you install `requirements.txt`

## License

This project is licensed under the MIT License.

![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg)
![GitHub stars](https://img.shields.io/github/stars/ADEL-MAHMOUD10/SubTranscribe.svg)
