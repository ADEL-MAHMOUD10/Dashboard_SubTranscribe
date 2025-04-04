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
        }).catch(error => {
            console.error('Error fetching upload ID:', error);
        });
    } catch (error) {
        console.error('Failed to initialize progress tracking:', error);
    }
}

function setupEventSource(uploadId) {
    // Use Server-Sent Events for real-time updates
    let eventSource = new EventSource(`/progress_stream/${uploadId}`);
    let lastUpdate = Date.now();
    let transcriptionStarted = false;
    
    eventSource.onmessage = (event) => {
        lastUpdate = Date.now();
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
    
    eventSource.onerror = () => {
        console.error('EventSource connection error, falling back to polling');
        eventSource.close();
        if (!pollingActive) {
            fallbackToPolling(uploadId);
        }
    };
    
    // Safety timeout - if no updates for 5 seconds during upload, fall back to polling
    const checkInterval = setInterval(() => {
        if (Date.now() - lastUpdate > 5000) {
            console.warn("No SSE updates for 5 seconds, falling back to polling");
            clearInterval(checkInterval);
            eventSource.close();
            if (!pollingActive) {
                fallbackToPolling(uploadId);
            }
        }
    }, 1000);
}

function fallbackToPolling(uploadId) {
    console.log("Activating fallback polling for upload ID:", uploadId);
    pollingActive = true;
    let transcriptionStarted = false;
    
    const progressPoll = setInterval(async () => {
        try {
            const response = await fetch(`/progress/${uploadId}`, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                credentials: 'include',
                cache: 'no-store'  // Prevent caching
            });

            if (!response.ok) {
                throw new Error(`Progress fetch failed: ${response.status}`);
            }

            const progress = await response.json();
            console.log("Poll Update:", progress);
            
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
                clearInterval(progressPoll);
                pollingActive = false;
            }
        } catch (error) {
            console.error('Error fetching progress:', error);
        }
    }, 1000);  // Poll every second
}

/**
 * Fetch upload ID from server
 */
async function fetchUploadId() {
    try {
        const response = await fetch('/upload_id', {
            method: 'GET',
            headers: { 'Accept': 'text/plain' },
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error(`Failed to get upload ID: ${response.status}`);
        }

        return await response.text();
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
    if (!progressMessage) return;
    
    progressMessage.textContent = message;
    progressMessage.style.color = isError 
        ? 'var(--error-color)' 
        : null; // Use default text color from Tailwind
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

// File upload with loading indicator
document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('uploadForm');
    const uploadLoading = document.getElementById('upload-loading');
    const fileInfo = document.getElementById('file-info');
    const progressContainer = document.querySelector('.progress-container');
    
    // Initialize global variable to track which form was submitted
    window.lastSubmittedForm = null;
    
    // Hide progress container initially
    if (progressContainer) {
        progressContainer.classList.add('hidden');
    }
    
    // File upload form handling
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            // Set which form was submitted
            window.lastSubmittedForm = 'file';
            
            // Hide file info and show loading spinner
            if (fileInfo) fileInfo.classList.add('hidden');
            if (uploadLoading) uploadLoading.classList.remove('hidden');
            
            // Show progress container for file uploads - will now be explicitly shown on form submit
            if (progressContainer) {
                progressContainer.classList.remove('hidden');
            }
        });
    }
    
    // Link form handling
    const linkForm = document.getElementById('linkForm');
    const linkLoading = document.getElementById('link-loading');
    
    if (linkForm) {
        linkForm.addEventListener('submit', function(e) {
            // Set which form was submitted
            window.lastSubmittedForm = 'link';
            
            // Show loading spinner
            if (linkLoading) linkLoading.classList.remove('hidden');
            
            // Show progress container but explicitly set progress to 0%
            if (progressContainer) {
                progressContainer.classList.remove('hidden');
                
                const progressBar = document.querySelector('.progress-bar');
                if (progressBar) {
                    progressBar.style.width = '0%';
                    progressBar.setAttribute('aria-valuenow', 0);
                }
                
                const progressMessage = document.getElementById('progressMessage');
                if (progressMessage) {
                    progressMessage.textContent = 'Initializing link extraction...';
                }
            }
            
            // You can add validation here if needed
            const linkInput = document.getElementById('link');
            if (linkInput && !linkInput.value.trim()) {
                e.preventDefault(); // Prevent form submission if link is empty
                alert('Please enter a valid URL');
                linkLoading.classList.add('hidden');
                
                // Hide progress container if validation fails
                if (progressContainer) {
                    progressContainer.classList.add('hidden');
                }
            }
        });
    }
});

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

/**
 * File Upload with Drag & Drop
 */
function initFileUpload() {
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('file');
    const uploadArea = document.querySelector('.upload-area');
    const progressContainer = document.querySelector('.progress-container');
    const progressBar = document.querySelector('.progress-bar');
    const browseBtn = document.querySelector('.browse-btn');
    const fileInfo = document.getElementById('file-info');
    
    if (!uploadForm || !fileInput) return;
    
    // Setup drag and drop
    if (uploadArea) {
        // Prevent default behavior
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
            uploadArea.addEventListener(event, e => {
                e.preventDefault();
                e.stopPropagation();
            });
        });
        
        // Add highlighting on drag
        ['dragenter', 'dragover'].forEach(event => {
            uploadArea.addEventListener(event, () => {
                uploadArea.classList.add('border-primary', 'bg-primary/5');
            });
        });
        
        // Remove highlighting when drag ends
        ['dragleave', 'drop'].forEach(event => {
            uploadArea.addEventListener(event, () => {
                uploadArea.classList.remove('border-primary', 'bg-primary/5');
            });
        });
        
        // Handle file drop
        uploadArea.addEventListener('drop', e => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                handleFileSelection(files[0]);
            }
        });
    }
    
    // File selection via browse button
    if (browseBtn) {
        browseBtn.addEventListener('click', () => {
            fileInput.click();
        });
    }
    
    // File selection change
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelection(fileInput.files[0]);
        }
    });
    
    // Form submission
    uploadForm.addEventListener('submit', e => {
        // Check if file is selected
        if (!fileInput.files || fileInput.files.length === 0) {
            updateProgressMessage('Please select a file first.', true);
            showProgressContainer();
            return;
        }
        
        // Clear progress UI
        resetProgressUI();
        
        // Submit the form - using the standard form submit to maintain backend compatibility
    });
    
    // Handle file selection
    function handleFileSelection(file) {
        // Validate file type
        const validTypes = ['audio/mpeg', 'audio/wav', 'video/mp4', 'audio/m4a'];
        if (!validTypes.includes(file.type)) {
            alert('Please upload a valid audio or video file.');
            return;
        }
        
        // Update UI with file info
        if (fileInfo) {
            const fileName = fileInfo.querySelector('.file-name');
            if (fileName) {
                // Format file size and append to filename
                const formattedSize = formatFileSize(file.size);
                fileName.innerHTML = `${file.name} <span class="text-sm text-gray-500">(${formattedSize})</span>`;
                fileInfo.classList.remove('hidden');
            }
        }
        
        // Don't show progress container until form is submitted
        if (progressContainer) {
            progressContainer.classList.add('hidden');
        }
    }
    
    // Reset progress UI - but don't show container
    function resetProgressUI() {
        if (progressBar) progressBar.style.width = '0%';
        
        // Progress message ID
        const progressMessage = document.getElementById('progressMessage');
        if (progressMessage) {
            progressMessage.textContent = '';
        }
    }
    
    // Show progress container
    function showProgressContainer() {
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
