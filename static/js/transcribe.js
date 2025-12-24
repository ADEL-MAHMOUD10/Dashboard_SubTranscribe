document.addEventListener('DOMContentLoaded', function () {
    AOS.init({ duration: 800, once: true });
    // document.getElementById('current-year').textContent = new Date().getFullYear(); // Removed to prevent error if footer missing

    // DOM Elements
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

    // CRITICAL: Global state to prevent duplicate submissions
    const state = {
        processingInterval: null,
        uploadInProgress: false,
        currentXHR: null,
        formSubmitted: false  // NEW: Track if form was already submitted
    };

    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.remove('dragover'), false);
    });

    dropArea.addEventListener('drop', handleDrop, false);
    fileInput.addEventListener('change', handleFileSelect);

    changeFileBtn.addEventListener('click', function () {
        fileInfo.style.display = 'none';
        dropArea.style.display = 'block';
        fileInput.value = '';
    });

    // ========== FILE FORM SUBMISSION ==========
    fileUploadForm.addEventListener('submit', function (e) {
        e.preventDefault();
        e.stopPropagation(); // CRITICAL: Stop event propagation

        // Prevent duplicate submissions
        if (state.uploadInProgress || state.formSubmitted) {
            console.warn('Upload already in progress, ignoring duplicate submission');
            showNotification('Upload already in progress', 'warning');
            return false;
        }

        if (fileInput.files.length > 0) {
            state.formSubmitted = true; // Mark as submitted
            uploadFileWithRealProgress(this);
        } else {
            showNotification('Please select a file first', 'error');
        }

        return false; // CRITICAL: Prevent default form submission
    });

    // ========== LINK FORM SUBMISSION ==========
    linkForm.addEventListener('submit', function (e) {
        e.preventDefault();
        e.stopPropagation(); // CRITICAL: Stop event propagation

        // Prevent duplicate submissions
        if (state.uploadInProgress || state.formSubmitted) {
            console.warn('Upload already in progress, ignoring duplicate submission');
            showNotification('Upload already in progress', 'warning');
            return false;
        }

        const linkInput = document.getElementById('linkInput');
        const url = linkInput.value.trim();

        if (!url) {
            showNotification('Please enter a valid URL', 'error');
            return false;
        }

        if (!isValidUrl(url) || !isSupportedDomain(url)) {
            showNotification('Please enter a supported media URL', 'error');
            return false;
        }

        state.formSubmitted = true; // Mark as submitted
        uploadLinkWithSimulatedProgress(this);

        return false; // CRITICAL: Prevent default form submission
    });

    // Helper functions
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function isValidUrl(string) {
        try {
            const url = new URL(string);
            return url.protocol === 'http:' || url.protocol === 'https:';
        } catch (_) {
            return false;
        }
    }

    function isSupportedDomain(url) {
        const supportedDomains = [
            'youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com',
            'twitch.tv', 'facebook.com', 'instagram.com', 'x.com', 'tiktok.com',
            'soundcloud.com', 'spotify.com', 'reddit.com', 'drive.google.com'
        ];

        const allowedExtensions = [
            '.mp3', '.wav', '.ogg', '.m4a', '.mp4', '.mov', '.webm', '.flac', '.aac', '.avi', '.mkv'
        ];

        try {
            const urlObj = new URL(url);
            const hostname = urlObj.hostname.toLowerCase();
            const pathname = urlObj.pathname.toLowerCase();

            const isKnownDomain = supportedDomains.some(domain =>
                hostname === domain || hostname.endsWith('.' + domain)
            );
            const hasAllowedExtension = allowedExtensions.some(ext => pathname.endsWith(ext));

            return isKnownDomain || hasAllowedExtension;
        } catch (_) {
            return false;
        }
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

            const maxSize = 500 * 1024 * 1024; // 500MB
            const allowedTypes = [
                'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/m4a', 'audio/aac', 'audio/ogg',
                'video/mp4', 'video/avi', 'video/mov', 'video/wmv', 'video/flv', 'video/webm'
            ];

            if (file.size > maxSize) {
                showNotification('File size must be less than 500MB', 'error');
                fileInput.value = '';
                return;
            }

            if (!allowedTypes.includes(file.type)) {
                showNotification('Please upload audio or video files only', 'error');
                fileInput.value = '';
                return;
            }

            fileName.textContent = file.name;
            fileSize.textContent = formatFileSize(file.size);
            fileTypeIcon.className = file.type.startsWith('audio/') ? 'fas fa-file-audio' : 'fas fa-file-video';

            fileInfo.style.display = 'block';
            dropArea.style.display = 'none';
        }
    }

    // ========== REAL UPLOAD PROGRESS (FILE) ==========
    function uploadFileWithRealProgress(form) {
        state.uploadInProgress = true;
        clearAllIntervals();

        // Disable form submission button
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Uploading...';
        }

        progressContainer.style.display = 'block';
        statusSteps.forEach(step => step.classList.remove('active', 'completed'));
        setStepStatus('upload', 'active');

        const formData = new FormData(form);
        const xhr = new XMLHttpRequest();
        state.currentXHR = xhr;

        updateProgress(0, 'Starting upload...');

        // Real upload progress
        xhr.upload.addEventListener('progress', function (e) {
            if (e.lengthComputable) {
                const uploadPercent = Math.round((e.loaded / e.total) * 80);

                let message = 'Uploading your file...';
                if (uploadPercent < 20) message = 'Starting upload...';
                else if (uploadPercent < 40) message = 'Uploading your file...';
                else if (uploadPercent < 60) message = 'Processing upload...';
                else message = 'Finalizing upload...';

                console.log(`Upload progress: ${e.loaded} / ${e.total} bytes (${uploadPercent}%)`);
                updateProgress(uploadPercent, message);
            }
        });

        // Upload complete
        xhr.upload.addEventListener('load', function () {
            console.log('Upload complete, processing...');
            updateProgress(80, 'Upload complete, processing...');
            startProcessingSimulation(80);
        });

        // Handle response
        xhr.addEventListener('load', function () {
            clearAllIntervals();

            if (xhr.status === 200 || xhr.status === 302) {
                const responseURL = xhr.responseURL;
                console.log('Response URL:', responseURL);

                handleRedirect(responseURL);
            } else {
                handleUploadError('Upload failed');
            }
        });

        xhr.addEventListener('error', () => handleUploadError('Network error'));
        xhr.addEventListener('timeout', () => handleUploadError('Upload timed out'));

        xhr.open('POST', form.action);
        xhr.timeout = 600000; // 10 minutes
        xhr.send(formData);
    }

    // ========== SIMULATED PROGRESS (LINK) ==========
    function uploadLinkWithSimulatedProgress(form) {
        state.uploadInProgress = true;
        clearAllIntervals();

        // Disable form submission button
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Processing...';
        }

        progressContainer.style.display = 'block';
        statusSteps.forEach(step => step.classList.remove('active', 'completed'));
        setStepStatus('upload', 'active');

        const formData = new FormData(form);

        let currentProgress = 0;
        updateProgress(0, 'Initializing...');

        const progressStages = [
            { threshold: 15, message: 'Connecting to source...' },
            { threshold: 30, message: 'Validating media link...' },
            { threshold: 50, message: 'Downloading content...' },
            { threshold: 70, message: 'Processing media...' },
            { threshold: 85, message: 'Analyzing speech patterns...' },
            { threshold: 95, message: 'Generating transcript...' }
        ];

        state.processingInterval = setInterval(() => {
            let increment;
            if (currentProgress < 70) increment = Math.random() * 2 + 1;
            else if (currentProgress < 85) increment = Math.random() * 0.5 + 0.3;
            else increment = Math.random() * 0.2 + 0.1;

            currentProgress = Math.min(99, currentProgress + increment);

            let message = 'Processing link...';
            for (let i = progressStages.length - 1; i >= 0; i--) {
                if (currentProgress >= progressStages[i].threshold) {
                    message = progressStages[i].message;
                    break;
                }
            }

            updateProgress(currentProgress, message);

            if (currentProgress >= 99) clearAllIntervals();
        }, 300);

        // Submit form (only once!)
        fetch(form.action, {
            method: 'POST',
            body: formData,
            redirect: 'follow'
        })
            .then(response => {
                clearAllIntervals();
                const finalUrl = response.url;
                console.log('Link upload final URL:', finalUrl);
                handleRedirect(finalUrl);
            })
            .catch(error => {
                console.error('Link upload error:', error);
                handleUploadError('Failed to process link');
            });
    }

    // ========== PROCESSING SIMULATION ==========
    function startProcessingSimulation(startPercent) {
        clearAllIntervals();

        let currentProgress = startPercent;

        state.processingInterval = setInterval(() => {
            const increment = Math.random() * 0.3 + 0.15;
            currentProgress = Math.min(99, currentProgress + increment);

            let message = 'Processing audio/video...';
            if (currentProgress >= 85 && currentProgress < 90) message = 'Analyzing speech patterns...';
            else if (currentProgress >= 90 && currentProgress < 95) message = 'Generating transcript...';
            else if (currentProgress >= 95) message = 'Finalizing transcript...';

            updateProgress(currentProgress, message);

            if (currentProgress >= 99) clearAllIntervals();
        }, 400);
    }

    // ========== REDIRECT HANDLER ==========
    function handleRedirect(url) {
        if (url.includes('job_status')) {
            updateProgress(100, 'Redirecting to status page...');
            setTimeout(() => window.location.href = url, 500);
        }
        else if (url.includes('download') || url.includes('subtitle')) {
            updateProgress(100, 'Processing complete!');
            setTimeout(() => window.location.href = url, 1000);
        }
        else if (url.includes('error')) {
            updateProgress(100, 'Error occurred', true);
            setTimeout(() => window.location.href = url, 1500);
        }
        else {
            updateProgress(100, 'Processing complete');
            setTimeout(() => window.location.href = url, 1000);
        }
    }

    // ========== ERROR HANDLER ==========
    function handleUploadError(errorMsg) {
        clearAllIntervals();
        updateProgress(100, errorMsg, true);
        showNotification(errorMsg + '. Please try again.', 'error');

        // Reset state
        state.uploadInProgress = false;
        state.formSubmitted = false;

        // Re-enable submit buttons
        document.querySelectorAll('button[type="submit"]').forEach(btn => {
            btn.disabled = false;
            btn.textContent = btn.getAttribute('data-original-text') || 'Submit';
        });
    }

    // ========== PROGRESS UPDATE ==========
    function updateProgress(percentage, message, isError = false) {
        const numericPercentage = parseFloat(percentage);
        const displayPercentage = Math.min(100, numericPercentage).toFixed(1);

        progressBar.style.width = displayPercentage + '%';
        progressBar.setAttribute('aria-valuenow', displayPercentage);
        progressMessage.textContent = message;

        const progressPercentage = document.getElementById('progressPercentage');
        if (progressPercentage) {
            progressPercentage.textContent = displayPercentage + '%';
        }

        progressMessage.className = 'progress-message';

        if (isError) {
            progressBar.classList.add('bg-danger');
            progressMessage.classList.add('error');
        } else {
            progressBar.classList.remove('bg-danger');
            progressMessage.classList.add(numericPercentage < 100 ? 'processing' : 'complete');
        }

        updateStatusAnimation(numericPercentage);
    }

    function updateStatusAnimation(percentage) {
        statusSteps.forEach(step => step.classList.remove('active', 'completed'));

        if (percentage <= 30) {
            setStepStatus('upload', 'active');
        } else if (percentage <= 60) {
            setStepStatus('upload', 'completed');
            setTimeout(() => setStepStatus('process', 'active'), 200);
        } else if (percentage <= 90) {
            setStepStatus('upload', 'completed');
            setStepStatus('process', 'completed');
            setTimeout(() => setStepStatus('analyze', 'active'), 200);
        } else if (percentage >= 100) {
            setStepStatus('upload', 'completed');
            setTimeout(() => {
                setStepStatus('process', 'completed');
                setTimeout(() => {
                    setStepStatus('analyze', 'completed');
                    setTimeout(() => setStepStatus('complete', 'completed'), 200);
                }, 200);
            }, 200);
        }
    }

    function setStepStatus(stepName, status) {
        const step = document.querySelector(`.status-step[data-step="${stepName}"]`);
        if (step) step.classList.add(status);
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    function clearAllIntervals() {
        if (state.processingInterval) {
            clearInterval(state.processingInterval);
            state.processingInterval = null;
        }
    }

    function showNotification(message, type) {
        const notification = document.getElementById('notification');
        if (!notification) return;

        notification.textContent = message;
        notification.className = 'notification-toast ' + type;
        notification.style.display = 'block';

        setTimeout(() => notification.style.display = 'none', 3000);
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        clearAllIntervals();
        if (state.currentXHR) state.currentXHR.abort();
    });
});