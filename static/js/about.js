document.addEventListener('DOMContentLoaded', () => {
    const description = "Transcription & Subtitles is a web-based tool that allows you to upload audio or video files and generate subtitles in .srt or .vtt formats. The platform supports a wide range of file formats and makes it easy to convert media into text for accessibility or convenience.";

    const supportedFiles = ["MP4", "WMV", "MOV", "MKV", "H.264", "MP3", "WAV"];

    const fileFormats = `
        <div class="col-md-5 mb-3 animate-box">
            <div class="card border-info shadow p-3">
                <h3 class="card-title text-center">SRT</h3>
                <p class="card-text text-center">SRT files are widely supported by most media players and video platforms. They are simple text files that store subtitle data with timecodes.</p>
            </div>
        </div>
        <div class="col-md-5 mb-3 animate-box">
            <div class="card border-primary shadow p-3">
                <h3 class="card-title text-center">VTT</h3>
                <p class="card-text text-center">VTT files are used in HTML5 video elements. They support additional features such as text styling, making them ideal for web-based platforms.</p>
            </div>
        </div>
    `;

    const usageInfo = `
        <div class="col-md-5 mb-3 animate-box">
            <div class="card border-success  shadow p-3">
                <h3 class="card-title text-center">How to Use on PC</h3>
                <p class="card-text text-center">
                    On PC, most media players like VLC, Windows Media Player, and others allow you to load subtitle files by dragging and dropping the SRT or VTT file onto the video player.
                </p>
            </div>
        </div>
        <div class="col-md-5 animate-box">
            <div class="card border-warning shadow p-3">
                <h3 class="card-title text-center">How to Use on Mobile</h3>
                <p class="card-text text-center">
                    On Mobile (Android or iOS), apps like MX Player, VLC, and Infuse allow you to load external subtitle files along with your media by selecting the subtitle file in the app’s settings.
                </p>
            </div>
        </div>
    `;

    document.getElementById('description').textContent = description;
    
    const fileList = document.getElementById('supported-files');
    supportedFiles.forEach(file => {
        const li = document.createElement('li');
        li.className = "list-group-item list-group-item-primary col-6 col-md-3";  // Added responsive classes here
        li.textContent = file;
        fileList.appendChild(li);
    });

    document.getElementById('file-formats').innerHTML = fileFormats;
    document.getElementById('usage-info').innerHTML = usageInfo;

    // Add animation
    const boxes = document.querySelectorAll('.animate-box');
    boxes.forEach(box => {
        box.style.transition = "transform 0.3s ease";
        box.addEventListener('mouseenter', () => {
            box.style.transform = "scale(1.05)";
        });
        box.addEventListener('mouseleave', () => {
            box.style.transform = "scale(1)";
        });
    });
});
