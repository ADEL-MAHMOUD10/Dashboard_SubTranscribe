/**
 * SubTranscribe - Frontend JavaScript
 * 
 * This script handles all frontend functionality for the SubTranscribe application:
 * - Theme toggling (light/dark mode)
 * - Mobile navigation 
 * - Tab switching between upload and link options
 * - File uploads with drag & drop support
 * - Progress tracking of transcription process
 * - Smooth scrolling
 * - Animations
 */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize form tracking
    window.lastSubmittedForm = null;
    
    // Initialize all app features
    initApp();
    
    // Start progress tracking for file uploads
    initProgressTracking();
});

/**
 * Initialize all application features
 */
function initApp() {
    initThemeToggle();
    initMobileNavigation();
    initTabSwitching();
    initFileUpload();
    initSmoothScrolling();
    initScrollReveal();
}

/**
 * Progress Tracking System
 */
let pollingActive = false;  // Define this globally
let uploadProgressTimer = null;

function initProgressTracking() {
    try {
        // Get upload ID from server
        fetchUploadId().then(uploadId => {
            if (!uploadId) {
                console.warn('No upload ID available, progress tracking disabled');
                return;
            }

            console.log("Setting up progress tracking for upload ID:", uploadId);

            // Try Server-Sent Events first but don't show progress elements yet
            setupEventSource(uploadId);
            
            // Set up a safety fallback in case SSE doesn't initialize properly
            setTimeout(() => {
                if (!pollingActive) {
                    console.warn("SSE might not have started properly, enabling polling as backup");
                    fallbackToPolling(uploadId);
                }
            }, 2000);
        }).catch(error => {
            console.error('Error fetching upload ID:', error);
        });
    } catch (error) {
        console.error('Failed to initialize progress tracking:', error);
    }
}

function setupEventSource(uploadId) {
    if (!uploadId || uploadId === 'undefined' || uploadId === 'null') {
        console.error('Invalid upload ID for SSE:', uploadId);
        return;
    }
    
    // Use Server-Sent Events for real-time updates
    let eventSource;
    let reconnectAttempts = 0;
    const maxReconnects = 3;
    let lastEventTime = Date.now();
    let transcriptionStarted = false;
    
    function createEventSource() {
        try {
            // Close any existing connection
            if (eventSource) {
                eventSource.close();
            }
            
            eventSource = new EventSource(`/progress_stream/${uploadId}`);
            lastEventTime = Date.now();
            
            eventSource.onmessage = (event) => {
                lastEventTime = Date.now();
                reconnectAttempts = 0; // Reset reconnect counter on successful message
                
                try {
                    const progress = JSON.parse(event.data);
                    
                    // Only show progress UI once we get real progress updates
                    if (progress.status > 0 || 
                        (progress.message && progress.message.toLowerCase().includes("upload"))) {
                        transcriptionStarted = true;
                    }
                    
                    if (transcriptionStarted) {
                        updateProgressUI(progress);
                    }
                    
                    console.log("SSE Update:", progress);
                    
                    // Close connection when complete but keep elements visible
                    if (progress.status >= 100 && progress.message.includes("complete")) {
                        console.log("Closing SSE connection - process complete");
                        eventSource.close();
                    }
                } catch (e) {
                    console.error("Error parsing SSE data:", e);
                }
            };
            
            eventSource.onerror = (e) => {
                console.error('EventSource connection error', e);
                
                // Only try to reconnect a limited number of times
                if (reconnectAttempts < maxReconnects) {
                    reconnectAttempts++;
                    console.log(`SSE reconnect attempt ${reconnectAttempts}/${maxReconnects}`);
                    
                    // Use exponential backoff for reconnection
                    setTimeout(() => {
                        createEventSource();
                    }, Math.min(1000 * Math.pow(2, reconnectAttempts), 8000));
                } else {
                    eventSource.close();
                    console.log("Maximum SSE reconnection attempts reached, falling back to polling");
                    if (!pollingActive) {
                        fallbackToPolling(uploadId);
                    }
                }
            };
        } catch (e) {
            console.error('Failed to create EventSource:', e);
            if (!pollingActive) {
                fallbackToPolling(uploadId);
            }
            return;
        }
    }
    
    // Create initial EventSource connection
    createEventSource();
    
    // Safety timeout - if no updates for 8 seconds during upload, fall back to polling
    const checkInterval = setInterval(() => {
        if (Date.now() - lastEventTime > 8000) {
            console.warn("No SSE updates for 8 seconds, falling back to polling");
            clearInterval(checkInterval);
            
            if (eventSource) {
                eventSource.close();
            }
            
            if (!pollingActive) {
                fallbackToPolling(uploadId);
            }
        }
    }, 2000); // Check every 2 seconds
}

function fallbackToPolling(uploadId) {
    if (!uploadId || uploadId === 'undefined' || uploadId === 'null') {
        console.error('Invalid upload ID for polling:', uploadId);
        return;
    }
    
    console.log("Activating fallback polling for upload ID:", uploadId);
    pollingActive = true;
    let transcriptionStarted = false;
    let consecutiveErrors = 0;
    let lastPercentage = 0;
    let noChangeCount = 0;
    let pollInterval = 1000; // Start with 1 second polling
    
    // Clear any existing timer
    if (uploadProgressTimer) {
        clearInterval(uploadProgressTimer);
    }
    
    // Function to perform the polling - this allows us to dynamically adjust the interval
    const performPoll = async () => {
        try {
            const response = await fetch(`/progress/${uploadId}`, {
                method: 'GET',
                headers: { 
                    'Accept': 'application/json',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                },
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error(`Progress fetch failed: ${response.status}`);
            }

            // Reset error counter on success
            consecutiveErrors = 0;
            
            const progress = await response.json();
            const currentPercentage = progress.status || 0;
            
            // Adjust polling frequency based on progress stage
            if (currentPercentage === lastPercentage) {
                noChangeCount++;
                
                // If no change for several polls, slow down polling
                if (noChangeCount > 3) {
                    // Exponential backoff with max 5 seconds
                    // Increase the polling interval using exponential backoff,
                    // but cap it at a maximum of 5 seconds to avoid excessive delays.
                    pollInterval = Math.min(pollInterval * 1.5, 5000);
                }
            } else {
                // Reset counter and interval when progress changes
                noChangeCount = 0;
                pollInterval = 1000;
                lastPercentage = currentPercentage;
            }
            
            // When progress is high, poll more frequently
            if (currentPercentage >= 95) {
                pollInterval = 800; // Faster polling at the end
            }
            
            console.log("Poll Update:", progress, "Next poll in:", pollInterval + "ms");
            
            // Only show progress UI once we get real progress updates
            if (progress.status > 0 || 
                (progress.message && progress.message.toLowerCase().includes("upload"))) {
                transcriptionStarted = true;
            }
            
            if (transcriptionStarted) {
                updateProgressUI(progress);
            }
            
            // Clear interval when complete
            if (progress.status >= 100 && progress.message.includes("complete")) {
                clearTimeout(uploadProgressTimer);
                pollingActive = false;
            } else {
                // Schedule next poll with dynamic interval
                uploadProgressTimer = setTimeout(performPoll, pollInterval);
            }
        } catch (error) {
            console.error('Error fetching progress:', error);
            consecutiveErrors++;
            
            // If we get too many consecutive errors, show a message but keep trying
            if (consecutiveErrors > 3) {
                updateProgressMessage("Connection issue, retrying...", true);
                // Increase poll interval on errors to avoid overwhelming server
                pollInterval = Math.min(pollInterval * 1.5, 8000);
            }
            
            // Schedule next poll even after error
            uploadProgressTimer = setTimeout(performPoll, pollInterval);
        }
    };
    
    // Start polling immediately
    performPoll();
}

/**
 * Fetch upload ID from server
 */
async function fetchUploadId() {
    try {
        const response = await fetch('/upload_id', {
            method: 'GET',
            headers: { 
                'Accept': 'text/plain',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            },
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error(`Failed to get upload ID: ${response.status}`);
        }

        const uploadId = await response.text();
        return uploadId && uploadId !== 'undefined' && uploadId !== 'null' ? uploadId : null;
    } catch (error) {
        console.error('Error getting upload ID:', error);
        return null;
    }
}

/**
 * Update progress UI with latest status
 */
function updateProgressUI(progressData) {
    const progressBar = document.querySelector('.progress-bar');
    const progressMessage = document.getElementById('progressMessage');
    const uploadLoading = document.getElementById('upload-loading');
    const linkLoading = document.getElementById('link-loading');
    const progressContainer = document.querySelector('.progress-container');
    
    if (!progressBar || !progressMessage) return;
    
    // Make sure progress container is visible when we have real progress data
    if (progressContainer && 
        (progressData.status > 0 || (progressData.message && progressData.message.includes("Upload")))) {
        progressContainer.classList.remove('hidden');
    }
    
    // Keep both loading spinner and progress bar visible during transcription
    if (progressData.message && 
        (progressData.message.toLowerCase().includes("upload") || 
         progressData.message.toLowerCase().includes("transcri") ||
         progressData.message.toLowerCase().includes("extract") ||
         progressData.message.toLowerCase().includes("transfer"))) {
        
        // Show the appropriate loading spinner based on which form was submitted
        if (window.lastSubmittedForm === 'link') {
            if (uploadLoading) uploadLoading.classList.add('hidden');
            if (linkLoading) linkLoading.classList.remove('hidden');
        } else {
            if (linkLoading) linkLoading.classList.add('hidden');
            if (uploadLoading) uploadLoading.classList.remove('hidden');
        }
    } else if (progressData.status >= 100) {
        // Only hide spinners when complete
        if (uploadLoading) uploadLoading.classList.add('hidden');
        if (linkLoading) linkLoading.classList.add('hidden');
    }
    
    // Check for error status (-1)
    if (progressData.status === -1) {
        // Connection problem but don't reset progress bar
        updateProgressMessage(progressData.message || "Connection issue, retrying...", true);
        return;
    }
    
    // Explicitly ensure progress bar starts at 0 if status is low
    if (progressData.status <= 5) {
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', 0);
    }
    
    // Get current progress from the bar
    const currentWidth = parseFloat(progressBar.style.width || '0');
    const newPercentage = typeof progressData.status === 'number' 
        ? progressData.status 
        : parseFloat(progressData.status) || 0;
    
    // Only update progress bar if new value is higher (prevents going backwards)
    if (newPercentage >= currentWidth) {
        // Add a subtle animation for smoother transitions
        progressBar.style.transition = 'width 0.5s ease-in-out';
        progressBar.style.width = `${newPercentage}%`;
        progressBar.setAttribute('aria-valuenow', newPercentage);
        
        // Update message based on progress
        if (newPercentage >= 100) {
            updateProgressMessage('Transcription successfully completed');
        } else {
            updateProgressMessage(progressData.message || `Processing ${newPercentage.toFixed(1)}%`);
        }
    } else {
        // If new value is lower, keep the message updated but don't reduce progress bar
        updateProgressMessage(progressData.message || `Processing ${currentWidth.toFixed(1)}%`);
    }
}

/**
 * Update progress message
 */
function updateProgressMessage(message, isError = false) {
    const progressMessage = document.getElementById('progressMessage');
    const progressError = document.querySelector('.progress-error');
    const errorMessage = progressError ? progressError.querySelector('.error-message') : null;
    
    if (!progressMessage) return;
    
    if (isError && progressError && errorMessage) {
        // Show error message in the dedicated error container
        progressMessage.style.display = 'none';
        errorMessage.textContent = message;
        progressError.classList.remove('hidden');
    } else {
        // Show normal progress message
        progressMessage.style.display = '';
        progressMessage.textContent = message;
        if (progressError) {
            progressError.classList.add('hidden');
        }
    }
}

/**
 * Theme Toggle Functionality
 */
function initThemeToggle() {
    const themeToggle = document.querySelector('.theme-toggle');
    if (!themeToggle) return;

    // Set initial theme based on localStorage or system preference
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    // Set initial theme
    if (savedTheme) {
        setTheme(savedTheme);
    } else if (prefersDark) {
        setTheme('dark');
    }

    // Toggle theme on click
    themeToggle.addEventListener('click', () => {
        const isDark = document.documentElement.classList.contains('dark');
        setTheme(isDark ? 'light' : 'dark');
    });
}

/**
 * Set theme and update icon and label
 */
function setTheme(theme) {
    if (theme === 'dark') {
        document.documentElement.classList.add('dark');
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.classList.remove('dark');
        document.documentElement.setAttribute('data-theme', 'light');
    }
    
    localStorage.setItem('theme', theme);
    
    // Update icon and label
    const icon = document.querySelector('.theme-toggle i');
    const label = document.querySelector('.theme-label');
    
    if (icon) {
        if (theme === 'dark') {
            icon.className = 'fas fa-moon text-purple-400';
        } else {
            icon.className = 'fas fa-sun text-amber-500';
        }
    }
    

    
    // Force browser to recalculate styles
    document.body.offsetHeight;
    
    // Update tab button colors if they exist
    const activeTab = document.querySelector('.tab-btn.active');
    if (activeTab) {
        // First remove any existing color classes
        activeTab.classList.remove('bg-primary', 'bg-darkPrimary', 'text-white');
        
        // Then add the appropriate ones based on theme
        if (theme === 'dark') {
            activeTab.classList.add('bg-darkPrimary', 'text-white');
        } else {
            activeTab.classList.add('bg-primary', 'text-white');
        }
    }
}

/**
 * Mobile Navigation 
 */
function initMobileNavigation() {
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (!navToggle || !navMenu) return;
    
    // Toggle menu on button click
    navToggle.addEventListener('click', () => {
        navMenu.classList.toggle('active');
        
        // Toggle aria-expanded attribute for accessibility
        const isExpanded = navToggle.getAttribute('aria-expanded') === 'true';
        navToggle.setAttribute('aria-expanded', !isExpanded);
        
        // Toggle background and visual state for the toggle button
        if (!isExpanded) {
            navToggle.classList.add('bg-gray-100', 'dark:bg-gray-800');
            navToggle.querySelector('i').classList.replace('fa-bars', 'fa-times');
            
            // Add animation class for menu items
            const navItems = navMenu.querySelectorAll('.nav-item');
            navItems.forEach((item, index) => {
                item.style.transitionDelay = `${index * 50}ms`;
                item.classList.add('fade-in-down');
            });
        } else {
            navToggle.classList.remove('bg-gray-100', 'dark:bg-gray-800');
            navToggle.querySelector('i').classList.replace('fa-times', 'fa-bars');
            
            // Remove animation classes
            navMenu.querySelectorAll('.nav-item').forEach(item => {
                item.style.transitionDelay = '0ms';
                item.classList.remove('fade-in-down');
            });
        }
    });
    
    // Close menu when clicking outside
    document.addEventListener('click', (event) => {
        if (navMenu.classList.contains('active') && 
            !navMenu.contains(event.target) && 
            !navToggle.contains(event.target)) {
            
            navMenu.classList.remove('active');
            navToggle.setAttribute('aria-expanded', 'false');
            navToggle.classList.remove('bg-gray-100', 'dark:bg-gray-800');
            
            // Reset icon
            const icon = navToggle.querySelector('i');
            if (icon && icon.classList.contains('fa-times')) {
                icon.classList.replace('fa-times', 'fa-bars');
            }
            
            // Remove animation classes
            navMenu.querySelectorAll('.nav-item').forEach(item => {
                item.style.transitionDelay = '0ms';
                item.classList.remove('fade-in-down');
            });
        }
    });
    
    // Add click handling for nav links on mobile
    const navLinks = navMenu.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth < 768) {
                navMenu.classList.remove('active');
                navToggle.setAttribute('aria-expanded', 'false');
                
                const icon = navToggle.querySelector('i');
                if (icon && icon.classList.contains('fa-times')) {
                    icon.classList.replace('fa-times', 'fa-bars');
                }
                
                navToggle.classList.remove('bg-gray-100', 'dark:bg-gray-800');
            }
        });
    });
}

/**
 * Tab Switching between Upload and Link options
 */
function initTabSwitching() {
    const tabs = document.querySelectorAll('.tab-btn');
    if (!tabs.length) return;
    
    // Create slider element for the active tab indicator
    const tabContainer = document.querySelector('.tabs');
    if (tabContainer && !document.querySelector('.tab-slider')) {
        const slider = document.createElement('div');
        slider.className = 'tab-slider';
        tabContainer.appendChild(slider);
    }
    
    const updateSliderPosition = (activeTab) => {
        const slider = document.querySelector('.tab-slider');
        if (!slider) return;
        
        // Position and size the slider to match the active tab
        slider.style.width = `${activeTab.offsetWidth}px`;
        slider.style.left = `${activeTab.offsetLeft}px`;
        
        // Apply theme-appropriate colors
        const isDarkMode = document.documentElement.classList.contains('dark') || 
                          document.documentElement.getAttribute('data-theme') === 'dark';
        
        if (isDarkMode) {
            slider.style.backgroundColor = 'var(--darkPrimary, #8b5cf6)';
        } else {
            slider.style.backgroundColor = 'var(--primary, #4f46e5)';
        }
    };
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.getAttribute('data-tab');
            if (!target) return;
            
            // Get the currently active tab content
            const activeContent = document.querySelector('.tab-content.active');
            const newContent = document.getElementById(`${target}-tab`);
            
            if (!activeContent || !newContent || activeContent === newContent) return;
            
            // Reset progress bar when switching tabs
            const progressBar = document.querySelector('.progress-bar');
            const progressMessage = document.getElementById('progressMessage');
            const progressContainer = document.querySelector('.progress-container');
            
            if (progressBar) {
                progressBar.style.width = '0%';
                progressBar.setAttribute('aria-valuenow', 0);
            }
            
            if (progressMessage) {
                progressMessage.textContent = '';
            }
            
            if (progressContainer) {
                progressContainer.classList.add('hidden');
            }
            
            // Hide both loading spinners when switching tabs
            const uploadLoading = document.getElementById('upload-loading');
            const linkLoading = document.getElementById('link-loading');
            
            if (uploadLoading) uploadLoading.classList.add('hidden');
            if (linkLoading) linkLoading.classList.add('hidden');
            
            // Determine animation direction
            const goingRight = Array.from(tabs).indexOf(tab) > 
                              Array.from(tabs).indexOf(document.querySelector('.tab-btn.active'));
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab-btn').forEach(t => {
                t.classList.remove('active');
                t.classList.remove('bg-primary', 'dark:bg-darkPrimary', 'bg-darkPrimary', 'text-white');
                t.classList.add('text-gray-500', 'dark:text-gray-400');
            });
            
            // Add active class to current tab
            tab.classList.add('active');
            
            // Check for dark mode and apply appropriate styles
            const isDarkMode = document.documentElement.classList.contains('dark') || 
                              document.documentElement.getAttribute('data-theme') === 'dark';
            
            if (isDarkMode) {
                tab.classList.add('bg-darkPrimary', 'text-white');
            } else {
                tab.classList.add('bg-primary', 'text-white');
            }
            
            tab.classList.remove('text-gray-500', 'dark:text-gray-400');
            
            // Animate the slide transition between tab contents
            activeContent.classList.add(goingRight ? 'slide-left' : 'slide-right');
            newContent.classList.add(goingRight ? 'slide-from-right' : 'slide-from-left');
            
            // After animation completes, reset classes and show new content
            setTimeout(() => {
                document.querySelectorAll('.tab-content').forEach(c => {
                    c.classList.remove('active', 'slide-left', 'slide-right', 'slide-from-left', 'slide-from-right');
                });
                newContent.classList.add('active');
            }, 300); // Match this duration with CSS transition duration
            
            // Update the slider position
            updateSliderPosition(tab);
        });
    });
    
    // Activate first tab by default if none is active
    if (!document.querySelector('.tab-btn.active') && tabs.length > 0) {
        tabs[0].click();
    } else if (document.querySelector('.tab-btn.active')) {
        // Update slider position on init for the active tab
        updateSliderPosition(document.querySelector('.tab-btn.active'));
    }
    
    // Update slider position on window resize
    window.addEventListener('resize', () => {
        const activeTab = document.querySelector('.tab-btn.active');
        if (activeTab) {
            updateSliderPosition(activeTab);
        }
    });
}

/**
 * Initialize the file upload functionality
 */
function initFileUpload() {
    const uploadForm = document.getElementById('uploadForm');
    const linkForm = document.getElementById('linkForm');
    const fileInput = document.getElementById('file');
    const uploadArea = document.querySelector('.upload-area');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.querySelector('.file-name');
    const browseBtn = document.querySelector('.browse-btn');
    
    if (!uploadForm || !fileInput || !uploadArea) return;
    
    // Set up listeners for file input
    fileInput.addEventListener('change', function() {
        if (this.files.length > 0) {
            handleFileSelection(this.files[0]);
        }
    });
    
    // Open file dialog when browse button is clicked
    if (browseBtn) {
        browseBtn.addEventListener('click', function(e) {
            e.preventDefault();
            fileInput.click();
        });
    }
    
    // Handle drag and drop events
    if (uploadArea) {
        // Prevent default behavior to allow drop
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, preventDefaults, false);
        });
        
        // Handle dragenter and dragover events
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, function() {
                uploadArea.classList.add('border-primary', 'dark:border-darkPrimary', 'bg-gray-50', 'dark:bg-gray-800');
            }, false);
        });
        
        // Handle dragleave and drop events
        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, function() {
                uploadArea.classList.remove('border-primary', 'dark:border-darkPrimary', 'bg-gray-50', 'dark:bg-gray-800');
            }, false);
        });
        
        // Handle file drop
        uploadArea.addEventListener('drop', function(e) {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                handleFileSelection(files[0]);
            }
        }, false);
        
        // Clicking anywhere in the upload area should open the file dialog
        uploadArea.addEventListener('click', function() {
            fileInput.click();
        });
    }
    
    // Handle form submissions
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            if (fileInput.files.length === 0) {
                // No file selected
                alert('Please select a file to upload.');
                return;
            }
            
            // Mark that we're submitting the file form
            window.lastSubmittedForm = 'file';
            
            // Reset progress UI
            resetProgressUI();
            
            // Hide file info and show loading
            if (fileInfo) fileInfo.classList.add('hidden');
            const uploadLoading = document.getElementById('upload-loading');
            if (uploadLoading) uploadLoading.classList.remove('hidden');
            
            // Get a fresh upload ID before submitting
            fetchUploadId().then(uploadId => {
                if (uploadId) {
                    // Set up progress tracking with the new ID
                    setupEventSource(uploadId);
                    
                    // Safety net in case SSE doesn't work
                    setTimeout(() => {
                        if (!pollingActive) {
                            fallbackToPolling(uploadId);
                        }
                    }, 1000);
                }
                
                // Submit the form
                this.submit();
            }).catch(error => {
                console.error('Error fetching upload ID:', error);
                // Submit anyway, even if we can't track progress
                this.submit();
            });
        });
    }
    
    // Handle link form submission
    if (linkForm) {
        linkForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const linkInput = document.getElementById('link');
            if (!linkInput.value) {
                alert('Please enter a valid URL.');
                return;
            }
            
            // Mark that we're submitting the link form
            window.lastSubmittedForm = 'link';
            
            // Reset progress UI
            resetProgressUI();
            
            // Show link loading indicator
            const linkLoading = document.getElementById('link-loading');
            if (linkLoading) linkLoading.classList.remove('hidden');
            
            // Get a fresh upload ID before submitting
            fetchUploadId().then(uploadId => {
                if (uploadId) {
                    // Set up progress tracking with the new ID
                    setupEventSource(uploadId);
                    
                    // Safety net in case SSE doesn't work
                    setTimeout(() => {
                        if (!pollingActive) {
                            fallbackToPolling(uploadId);
                        }
                    }, 1000);
                }
                
                // Submit the form
                this.submit();
            }).catch(error => {
                console.error('Error fetching upload ID:', error);
                // Submit anyway, even if we can't track progress
                this.submit();
            });
        });
    }
    
    // Helper function to prevent default behavior
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    /**
     * Handle file selection - display file name and size
     */
    function handleFileSelection(file) {
        if (!fileInfo || !fileName) return;
        
        // Validate file type
        const fileType = file.type.split('/')[0];
        if (fileType !== 'audio' && fileType !== 'video') {
            alert('Please select an audio or video file.');
            return;
        }
        
        // Format display of file name with size
        const size = formatFileSize(file.size);
        fileName.textContent = `${file.name} (${size})`;
        
        // Show file info section and hide other elements
        fileInfo.classList.remove('hidden');
        
        // Reset progress UI
        resetProgressUI();
    }
    
    /**
     * Reset progress UI elements
     */
    function resetProgressUI() {
        const progressBar = document.querySelector('.progress-bar');
        const progressMessage = document.getElementById('progressMessage');
        const progressContainer = document.querySelector('.progress-container');
        const progressError = document.querySelector('.progress-error');
        
        if (progressBar) progressBar.style.width = '0%';
        if (progressMessage) progressMessage.textContent = 'Preparing...';
        if (progressContainer) progressContainer.classList.remove('hidden');
        if (progressError) progressError.classList.add('hidden');
    }
    
    /**
     * Show progress container
     */
    function showProgressContainer() {
        const progressContainer = document.querySelector('.progress-container');
        if (progressContainer) {
            progressContainer.classList.remove('hidden');
        }
    }
}

/**
 * Smooth Scrolling and Scroll-to-Top functionality
 */
function initSmoothScrolling() {
    // Handle anchor links
    document.querySelectorAll('a[href^="#"]:not([href="#"])').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            
            const target = document.querySelector(this.getAttribute('href'));
            if (!target) return;
            
            const header = document.querySelector('nav');
            const headerHeight = header ? header.offsetHeight : 0;
            const elementPosition = target.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - headerHeight;
            
            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
            
            // Close mobile menu if open
            closeMobileMenu();
        });
    });

    // Add scroll-to-top button
    const scrollButton = createScrollToTopButton();
    document.body.appendChild(scrollButton);
    
    // Show/hide scroll button
    window.addEventListener('scroll', () => {
        if (window.pageYOffset > 500) {
            scrollButton.classList.remove('opacity-0', 'invisible');
            scrollButton.classList.add('opacity-100', 'visible');
        } else {
            scrollButton.classList.add('opacity-0', 'invisible');
            scrollButton.classList.remove('opacity-100', 'visible');
        }
    });
}

/**
 * Create scroll to top button
 */
function createScrollToTopButton() {
    const button = document.createElement('button');
    button.className = 'fixed bottom-6 right-6 bg-primary dark:bg-darkPrimary text-white p-3 rounded-full shadow-lg cursor-pointer transition-all duration-300 opacity-0 invisible hover:bg-primary-dark dark:hover:bg-darkPrimary-dark z-50 group';
    button.innerHTML = `
        <i class="fas fa-arrow-up text-lg group-hover:animate-bounce"></i>
        <span class="sr-only">Scroll to top</span>
    `;
    
    button.addEventListener('click', () => {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
    
    return button;
}

/**
 * Close mobile menu helper
 */
function closeMobileMenu() {
    const navMenu = document.querySelector('.nav-menu');
    const navToggle = document.querySelector('.nav-toggle');
    if (navMenu && navMenu.classList.contains('active')) {
        navMenu.classList.remove('active');
        if (navToggle) {
            navToggle.setAttribute('aria-expanded', 'false');
            navToggle.classList.remove('bg-gray-100', 'dark:bg-gray-800');
            const icon = navToggle.querySelector('i');
            if (icon && icon.classList.contains('fa-times')) {
                icon.classList.replace('fa-times', 'fa-bars');
            }
        }
    }
}

/**
 * Scroll Reveal and Animations
 */
function initScrollReveal() {
    if (!('IntersectionObserver' in window)) return;
    
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // Handle both fade-in and scroll-reveal animations
                if (entry.target.classList.contains('fade-in')) {
                    entry.target.classList.add('opacity-100', 'translate-y-0');
                    entry.target.classList.remove('opacity-0', 'translate-y-5');
                }
                if (entry.target.classList.contains('scroll-reveal')) {
                    entry.target.classList.add('reveal');
                }
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    // Observe both fade-in and scroll-reveal elements
    document.querySelectorAll('.fade-in, .scroll-reveal').forEach(element => {
        if (element.classList.contains('fade-in')) {
            element.classList.add('opacity-0', 'translate-y-5', 'transition-all', 'duration-700');
        }
        observer.observe(element);
    });
}

/**
 * Format file size in human-readable format
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}