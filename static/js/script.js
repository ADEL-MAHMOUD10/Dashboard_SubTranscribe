// Reset the progress when the page loads
window.addEventListener('DOMContentLoaded', (event) => {
    // Reset the progress bar
    const progressBar = document.getElementById('progressBar');
    const messageElement = document.getElementById('progressMessage');

    progressBar.style.width = '0%';
    progressBar.setAttribute('aria-valuenow', 0);
    progressBar.textContent = '0%';
    messageElement.innerText = 'Ready to upload'; // You can set this to any initial message

    // Optionally reset the backend status
    resetProgressStatus();
});

const getUploadId = async () => {
    try {
        const response = await fetch('/upload_id', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const uploadId = await response.json();
        return uploadId;
    } catch (error) {
        console.error('Error fetching upload_id:', error);
        return null;
    }
};

const startProgressTracking = async () => {
    const UPLOAD_ID = await getUploadId();  
    
    if (!UPLOAD_ID) {
        console.error("Failed to retrieve upload ID");
        document.getElementById('progressMessage').innerText = "Failed to retrieve upload ID.";
        return;
    }

    console.log("Upload ID:", UPLOAD_ID);  
    
    const intervalId = setInterval(async function () {
        try {
            const url = `/progress/${UPLOAD_ID}`;
            console.log("Fetching progress from:", url);  
            
            const response = await fetch(url, {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`Network response was not ok: ${response.status}`);
            }

            const data = await response.json();
            console.log("Progress Data:", data);

            if (data && typeof data.status !== 'undefined') {
                const progressPercentage = parseFloat(data.status) || 0;
                const progressBar = document.getElementById('progressBar');
                progressBar.style.width = `${progressPercentage}%`;
                progressBar.setAttribute('aria-valuenow', progressPercentage);
                progressBar.textContent = `${progressPercentage.toFixed(2)}%`;

                if (progressPercentage === 100) {
                    clearInterval(intervalId);
                }
            }
        } catch (error) {
            console.error('Error fetching progress:', error);
        }
    }, 2500);
};

startProgressTracking();


// Display selected file name dynamically
function showFileName() {
    const fileInput = document.getElementById("file");
    const fileName = document.getElementById("fileName");
    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);  
        fileName.style.display = 'block';
        fileName.innerText = `File Selected: ${file.name} (${fileSizeMB} MB)`;
    }
}


function showWarningMessage() {
    const linkInput = document.getElementById('link').value;
    if (linkInput) {
        const warningModal = document.getElementById('messageModal');
        const warningText = `
            Some links (like YouTube and Twitter) may not work at the moment.
            Please ensure the link points directly to an audio or video file.
        `;
        warningModal.querySelector('p').innerText = warningText;
        warningModal.style.display = 'block';
    }
}

// Close modal functionality
document.querySelector('.close-button').addEventListener('click', function() {
    document.getElementById('messageModal').style.display = 'none';
});

window.onclick = function(event) {
    const modal = document.getElementById('messageModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
};
