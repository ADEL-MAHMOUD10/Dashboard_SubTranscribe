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
    const statusSteps = document.querySelectorAll('.status-step');
    
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
        
        // Reset status animation
        statusSteps.forEach(step => {
            step.classList.remove('active', 'completed');
        });
        setStepStatus('upload', 'active');
        
        // Create form data
        const formData = new FormData(form);
        
        // Create and configure XMLHttpRequest
        const xhr = new XMLHttpRequest();
        xhr.open('POST', form.action);
        
        // Track upload progress
        xhr.upload.addEventListener('progress', function(e) {
            if (e.lengthComputable) {
                // Calculate percentage (0-80% for upload)
                const percentage = Math.round((e.loaded / e.total) * 80);
                let message = 'Uploading your file...';
                
                if (percentage < 20) {
                    message = 'Starting upload...';
                } else if (percentage < 40) {
                    message = 'Uploading your file...';
                } else if (percentage < 60) {
                    message = 'Processing upload...';
                } else {
                    message = 'Finalizing upload...';
                }
                
                updateProgress(percentage, message);
                
                // Start slow progress once we reach 80%
                if (percentage >= 80 && !window.slowProgressStarted) {
                    window.slowProgressStarted = true;
                    startSlowProgress(80, null, xhr);
                }
            }
        });
        
        // Handle response
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                // Clear any existing intervals
                if (window.currentProgressInterval) {
                    clearInterval(window.currentProgressInterval);
                }
                
                if (xhr.status === 200) {
                    // Redirect URL handling
                    const redirectUrl = xhr.responseURL;
                    
                    // Check if we're being redirected to the subtitle page (success)
                    if (redirectUrl.includes('download') || redirectUrl.includes('subtitle')) {
                        // Processing is complete, jump to 100%
                        updateProgress(100, 'Processing complete!');
                        
                        // Delay redirect briefly to show completion
                        setTimeout(function() {
                            window.location.href = redirectUrl;
                        }, 1000);
                    } 
                    // Check if we're being redirected to an error page
                    else if (redirectUrl.includes('error')) {
                        updateProgress(100, 'Error processing file', true);
                        setTimeout(function() {
                            window.location.href = redirectUrl;
                        }, 1000);
                    }
                    // Otherwise continue with slow progress
                    else if (!window.slowProgressStarted) {
                        // Start slow progress after 80%
                        window.slowProgressStarted = true;
                        startSlowProgress(80, redirectUrl, xhr);
                    }
                } else {
                    updateProgress(100, 'Error processing file', true);
                    showNotification('Error processing file', 'error');
                }
            }
        };
        
        // Reset slow progress flag
        window.slowProgressStarted = false;
        
        // Start upload
        updateProgress(0, 'Preparing your file...');
        xhr.send(formData);
    }
    
    // Function to start slow progress after reaching 80%
    function startSlowProgress(startProgress, redirectUrl, xhr) {
        let currentProgress = startProgress;
        
        // Clear any existing interval
        if (window.currentProgressInterval) {
            clearInterval(window.currentProgressInterval);
        }
        
        const progressInterval = setInterval(function() {
            // Very small increments for slower animation
            const increment = 0.1 + (Math.random() * 0.2);
            currentProgress += increment;
            
            // Update messages based on progress
            let message = 'Processing audio/video...';
            
            if (currentProgress >= 85 && currentProgress < 90) {
                message = 'Analyzing speech patterns...';
            } else if (currentProgress >= 90 && currentProgress < 95) {
                message = 'Generating transcript...';
            } else if (currentProgress >= 95) {
                message = 'Finalizing transcript...';
            }
            
            // Update the progress bar with limited decimal places
            const displayProgress = Math.min(currentProgress, 99).toFixed(1);
            updateProgress(displayProgress, message);
            
            // If we receive a response that processing is complete, jump to 100%
            if (xhr && xhr.readyState === 4 && xhr.status === 200) {
                if (xhr.responseURL && (xhr.responseURL.includes('download') || xhr.responseURL.includes('subtitle'))) {
                    clearInterval(progressInterval);
                    updateProgress(100, 'Processing complete!');
                    
                    // Redirect to the result page
                    setTimeout(function() {
                        window.location.href = xhr.responseURL;
                    }, 1000);
                }
            }
            
            // Never go beyond 99% until processing is confirmed complete
            if (currentProgress >= 99) {
                clearInterval(progressInterval);
            }
        }, 300); // Update more frequently for smoother animation
        
        // Store the interval so it can be cleared if needed
        window.currentProgressInterval = progressInterval;
    }
    
    function uploadLink(form) {
        // Show progress container
        progressContainer.style.display = 'block';
        
        // Reset status animation
        statusSteps.forEach(step => {
            step.classList.remove('active', 'completed');
        });
        setStepStatus('upload', 'active');
        
        // Create form data
        const formData = new FormData(form);
        
        // Create and configure XMLHttpRequest
        const xhr = new XMLHttpRequest();
        xhr.open('POST', form.action);
        
        // Handle response
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                // Clear any existing intervals
                if (window.progressInterval) {
                    clearInterval(window.progressInterval);
                }
                if (window.currentProgressInterval) {
                    clearInterval(window.currentProgressInterval);
                }
                
                if (xhr.status === 200) {
                    const redirectUrl = xhr.responseURL;
                    
                    // Check if we're being redirected to the subtitle page (success)
                    if (redirectUrl.includes('download') || redirectUrl.includes('subtitle')) {
                        // Processing is complete, jump to 100%
                        updateProgress(100, 'Processing complete!');
                        
                        // Delay redirect briefly to show completion
                        setTimeout(function() {
                            window.location.href = redirectUrl;
                        }, 1000);
                    }
                    // Check if we're being redirected to an error page
                    else if (redirectUrl.includes('error')) {
                        updateProgress(100, 'Error processing link', true);
                        setTimeout(function() {
                            window.location.href = redirectUrl;
                        }, 1000);
                    }
                    // Otherwise continue with slow progress
                    else if (!window.slowProgressStarted) {
                        // Start slow progress after 80%
                        window.slowProgressStarted = true;
                        startSlowProgress(80, redirectUrl, xhr);
                    }
                } else {
                    updateProgress(100, 'Error processing link', true);
                    showNotification('Error processing link', 'error');
                }
            }
        };
        
        // Reset slow progress flag
        window.slowProgressStarted = false;
        
        // Start upload with simulated progress for links
        updateProgress(0, 'Initializing...');
        xhr.send(formData);
        
        // Define progress stages with thresholds and messages
        const progressStages = [
            { threshold: 10, message: 'Connecting to source...', step: 'upload' },
            { threshold: 25, message: 'Validating media link...', step: 'upload' },
            { threshold: 40, message: 'Downloading content...', step: 'upload' },
            { threshold: 55, message: 'Processing media...', step: 'upload' },
            { threshold: 70, message: 'Finalizing upload...', step: 'upload' },
            { threshold: 80, message: 'Analyzing speech patterns...', step: 'analyze' }
        ];
        
        // Create a more realistic progression
        let currentProgress = 0;
        const targetProgress = 80; // Stop at 80% and then switch to slow progress
        
        window.progressInterval = setInterval(function() {
            // Increment by smaller amounts for smoother animation
            // Slower at the beginning and end, faster in the middle
            let increment;
            if (currentProgress < 30) {
                increment = Math.max(1, Math.floor(Math.random() * 2));
            } else if (currentProgress < 70) {
                increment = Math.max(1, Math.floor(Math.random() * 3));
            } else {
                increment = Math.max(0.5, Math.floor(Math.random() * 1.5));
            }
            
            currentProgress += increment;
            
            // Find appropriate message and step for current progress
            let currentMessage = 'Processing link...';
            let currentStep = 'upload';
            
            for (let i = progressStages.length - 1; i >= 0; i--) {
                if (currentProgress >= progressStages[i].threshold) {
                    currentMessage = progressStages[i].message;
                    currentStep = progressStages[i].step;
                    break;
                }
            }
            
            // Update the progress
            updateProgress(currentProgress, currentMessage);
            
            // Stop when we reach target progress and start slow progress
            if (currentProgress >= targetProgress) {
                clearInterval(window.progressInterval);
                
                // Start slow progress once we reach 80%
                if (!window.slowProgressStarted) {
                    window.slowProgressStarted = true;
                    startSlowProgress(80, null, xhr);
                }
            }
        }, 300); // Update more frequently for smoother animation
    }
    
    function updateProgress(percentage, message, isError = false) {
        // Convert to number and limit decimal places for display
        const numericPercentage = parseFloat(percentage);
        const displayPercentage = numericPercentage.toFixed(1);
        
        progressBar.style.width = displayPercentage + '%';
        progressBar.setAttribute('aria-valuenow', displayPercentage);
        progressMessage.textContent = message;
        
        // Update percentage display
        const progressPercentage = document.getElementById('progressPercentage');
        if (progressPercentage) {
            progressPercentage.textContent = displayPercentage + '%';
        }
        
        // Handle message styling based on state
        progressMessage.className = 'progress-message';
        
        if (isError) {
            progressBar.classList.add('bg-danger');
            progressMessage.classList.add('error');
        } else {
            progressBar.classList.remove('bg-danger');
            
            if (numericPercentage < 100) {
                progressMessage.classList.add('processing');
            } else {
                progressMessage.classList.add('complete');
            }
        }
        
        // Update status animation
        updateStatusAnimation(numericPercentage);
    }
    
    function updateStatusAnimation(percentage) {
        // Reset all steps
        statusSteps.forEach(step => {
            step.classList.remove('active', 'completed');
        });
        
        // Update steps based on percentage with sequential animation
        if (percentage <= 30) {
            // Uploading phase
            setStepStatus('upload', 'active');
        } else if (percentage <= 60) {
            // Processing phase - complete upload first, then activate process
            setStepStatus('upload', 'completed');
            
            // Add a small delay before showing the next step as active
            setTimeout(() => {
                setStepStatus('process', 'active');
            }, 300);
        } else if (percentage <= 90) {
            // Analyzing phase - complete previous steps first, then activate analyze
            setStepStatus('upload', 'completed');
            setStepStatus('process', 'completed');
            
            // Add a small delay before showing the next step as active
            setTimeout(() => {
                setStepStatus('analyze', 'active');
            }, 300);
        } else if (percentage >= 100) {
            // Complete phase - complete all steps sequentially
            setStepStatus('upload', 'completed');
            
            setTimeout(() => {
                setStepStatus('process', 'completed');
                
                setTimeout(() => {
                    setStepStatus('analyze', 'completed');
                    
                    setTimeout(() => {
                        setStepStatus('complete', 'completed');
                    }, 300);
                }, 300);
            }, 300);
        }
    }
    
    function setStepStatus(stepName, status) {
        const step = document.querySelector(`.status-step[data-step="${stepName}"]`);
        if (step) {
            step.classList.add(status);
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