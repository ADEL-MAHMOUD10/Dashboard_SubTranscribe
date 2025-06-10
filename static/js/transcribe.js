/**
 * SubTranscribe - Transcription Page JavaScript
 * This script handles the file upload, progress tracking, and UI interactions for the transcription page.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize AOS
    AOS.init({
        duration: 800,
        once: true
    });
    
    // Set current year in footer
    document.getElementById('current-year').textContent = new Date().getFullYear();
    
    // File upload functionality
    const dropArea = document.getElementById('dropArea');
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const fileTypeIcon = document.getElementById('fileTypeIcon');
    const changeFileBtn = document.getElementById('changeFileBtn');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressMessage = document.getElementById('progressMessage');
    const fileUploadForm = document.getElementById('fileUploadForm');
    const linkForm = document.getElementById('linkForm');
    
    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    // Highlight drop area when dragging over it
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, unhighlight, false);
    });
    
    // Handle dropped files
    dropArea.addEventListener('drop', handleDrop, false);
    
    // Handle file input change
    fileInput.addEventListener('change', handleFileSelect);
    
    // Handle change file button
    changeFileBtn.addEventListener('click', function() {
        fileInfo.style.display = 'none';
        dropArea.style.display = 'block';
        fileInput.value = '';
    });
    
    // Handle form submissions
    fileUploadForm.addEventListener('submit', function(e) {
        e.preventDefault();
        if (fileInput.files.length > 0) {
            uploadFile(this);
        } else {
            showNotification('Please select a file first', 'error');
        }
    });
    
    linkForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const linkInput = document.getElementById('linkInput');
        if (linkInput.value.trim() !== '') {
            uploadLink(this);
        } else {
            showNotification('Please enter a valid URL', 'error');
        }
    });
    
    // Helper functions
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight() {
        dropArea.classList.add('dragover');
    }
    
    function unhighlight() {
        dropArea.classList.remove('dragover');
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            fileInput.files = files;
            handleFileSelect();
        }
    }
    
    function handleFileSelect() {
        if (fileInput.files.length > 0) {
            const file = fileInput.files[0];
            
            // Update file info
            fileName.textContent = file.name;
            fileSize.textContent = formatFileSize(file.size);
            
            // Set appropriate icon based on file type
            if (file.type.startsWith('audio/')) {
                fileTypeIcon.className = 'fas fa-file-audio';
            } else if (file.type.startsWith('video/')) {
                fileTypeIcon.className = 'fas fa-file-video';
            } else {
                fileTypeIcon.className = 'fas fa-file';
            }
            
            // Show file info and hide drop area
            fileInfo.style.display = 'block';
            dropArea.style.display = 'none';
        }
    }
    
    function uploadFile(form) {
        // Show progress container
        progressContainer.style.display = 'block';
        
        // Create form data
        const formData = new FormData(form);
        
        // Create and configure XMLHttpRequest
        const xhr = new XMLHttpRequest();
        xhr.open('POST', form.action);
        
        // Track upload progress
        xhr.upload.addEventListener('progress', function(e) {
            if (e.lengthComputable) {
                // Calculate percentage (0-90% for upload)
                const percentage = Math.round((e.loaded / e.total) * 90);
                let message = 'Uploading your file...';
                
                if (percentage < 20) {
                    message = 'Starting upload...';
                } else if (percentage < 50) {
                    message = 'Uploading your file...';
                } else if (percentage < 80) {
                    message = 'Almost there...';
                } else {
                    message = 'Finalizing upload...';
                }
                
                updateProgress(percentage, message);
            }
        });
        
        // Handle response
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    // Show 90-100% for processing
                    updateProgress(92, 'Processing audio/video...');
                    
                    // Simulate processing steps
                    setTimeout(() => updateProgress(95, 'Analyzing content...'), 800);
                    setTimeout(() => updateProgress(98, 'Generating transcript...'), 1600);
                    setTimeout(() => {
                        // Show 100% before redirecting
                        updateProgress(100, 'Processing complete!');
                        
                        // Delay redirect to show 100% progress
                        setTimeout(function() {
                            window.location.href = xhr.responseURL;
                        }, 1000);
                    }, 2400);
                } else {
                    updateProgress(100, 'Error processing file', true);
                    showNotification('Error processing file', 'error');
                }
            }
        };
        
        // Start upload
        updateProgress(0, 'Preparing your file...');
        xhr.send(formData);
    }
    
    function uploadLink(form) {
        // Show progress container
        progressContainer.style.display = 'block';
        
        // Create form data
        const formData = new FormData(form);
        
        // Create and configure XMLHttpRequest
        const xhr = new XMLHttpRequest();
        xhr.open('POST', form.action);
        
        // Handle response
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    // Show 100% before redirecting
                    updateProgress(100, 'Processing complete!');
                    
                    // Clear any existing intervals
                    if (window.progressInterval) {
                        clearInterval(window.progressInterval);
                    }
                    
                    // Delay redirect to show 100% progress
                    setTimeout(function() {
                        window.location.href = xhr.responseURL;
                    }, 1000);
                } else {
                    updateProgress(100, 'Error processing link', true);
                    showNotification('Error processing link', 'error');
                }
            }
        };
        
        // Start upload with simulated progress for links
        updateProgress(0, 'Initializing...');
        xhr.send(formData);
        
        // Simulate progress for link processing with better messages
        let progress = 0;
        const messages = [
            { threshold: 10, message: 'Connecting to source...' },
            { threshold: 30, message: 'Validating media link...' },
            { threshold: 50, message: 'Downloading content...' },
            { threshold: 70, message: 'Preparing for transcription...' },
            { threshold: 85, message: 'Processing audio tracks...' }
        ];
        
        window.progressInterval = setInterval(function() {
            progress += 5;
            if (progress <= 90) {
                // Find appropriate message for current progress
                let currentMessage = 'Processing link...';
                for (let i = messages.length - 1; i >= 0; i--) {
                    if (progress >= messages[i].threshold) {
                        currentMessage = messages[i].message;
                        break;
                    }
                }
                updateProgress(progress, currentMessage);
            } else {
                clearInterval(window.progressInterval);
            }
        }, 500);
    }
    
    function updateProgress(percentage, message, isError = false) {
        progressBar.style.width = percentage + '%';
        progressBar.setAttribute('aria-valuenow', percentage);
        progressMessage.textContent = message;
        
        // Update percentage display
        const progressPercentage = document.getElementById('progressPercentage');
        if (progressPercentage) {
            progressPercentage.textContent = percentage + '%';
        }
        
        // Handle message styling based on state
        progressMessage.className = 'progress-message';
        
        if (isError) {
            progressBar.classList.add('bg-danger');
            progressMessage.classList.add('error');
        } else {
            progressBar.classList.remove('bg-danger');
            
            if (percentage < 100) {
                progressMessage.classList.add('processing');
            } else {
                progressMessage.classList.add('complete');
            }
        }
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    function showNotification(message, type) {
        const notification = document.getElementById('notification');
        notification.textContent = message;
        notification.className = 'notification-toast ' + type;
        notification.style.display = 'block';
        
        setTimeout(() => {
            notification.style.display = 'none';
        }, 3000);
    }
}); 