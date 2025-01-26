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

function resetProgressStatus() {
    fetch('/reset-progress', { method: 'GET' })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok.');
            }
            return response.json();
        })
        .then(data => {
            console.log('Progress reset:', data);
        })
        .catch(error => {
            console.error('Error resetting progress:', error);
        });
}

// Continue with your interval function
const intervalId = setInterval(async function () {
    try {
        const response = await fetch('/v1/{{ upload_id }}/progress', {
            method: 'GET',
            credentials: 'include',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error('Network response was not ok.');
        }
        
        const data = await response.json();
        console.log("Progress Data:", data);
        
        if (data && typeof data.status !== 'undefined') {
            const progressPercentage = parseFloat(data.status) || 0;
            
            const progressBar = document.getElementById('progressBar');
            progressBar.style.width = `${progressPercentage}%`;
            progressBar.style.transition = 'width 0.5s ease';
            progressBar.setAttribute('aria-valuenow', progressPercentage);
            progressBar.textContent = `${progressPercentage.toFixed(2)}%`;
            
            const messageElement = document.getElementById('progressMessage');
            messageElement.innerText = data.message;
            
            // Change color based on progress.
            if (progressPercentage === 100) {
                progressBar.style.backgroundColor = 'green'; // Success color
                messageElement.textContent = "Upload completed. Please wait for a few seconds...";
                clearInterval(intervalId);  // Stop polling
                // Optionally trigger additional completion logic here
            } else if (progressPercentage >= 50) {
                progressBar.style.backgroundColor = 'orange'; // Warning color
            } else {
                progressBar.style.backgroundColor = 'blue'; // Default color
            }
        }
    } catch (error) {
        console.error('Error fetching progress:', error);
        document.getElementById('progressMessage').innerText = "Error fetching progress. Please try again.";
    }
}, 1000);  // Poll every 1 seconds


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
