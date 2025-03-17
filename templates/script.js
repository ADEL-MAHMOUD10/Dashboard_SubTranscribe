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
    initAnimations();
}

/**
 * Progress Tracking System
 */
async function initProgressTracking() {
    try {
        // Get upload ID from server
        const uploadId = await fetchUploadId();
        if (!uploadId) {
            console.warn('No upload ID available, progress tracking disabled');
            updateProgressMessage('Ready to upload');
            return;
        }

        // Start polling for progress updates
        const pollingInterval = 2000; // 2 seconds
        const progressPoll = setInterval(async () => {
            try {
                const progress = await fetchProgress(uploadId);
                updateProgressUI(progress);
                
                // Clear interval when complete
                if (progress.status >= 100) {
                    clearInterval(progressPoll);
                }
            } catch (error) {
                console.error('Error fetching progress:', error);
            }
        }, pollingInterval);
    } catch (error) {
        console.error('Failed to initialize progress tracking:', error);
    }
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
 * Fetch progress data for a specific upload
 */
async function fetchProgress(uploadId) {
    if (!uploadId) return { status: 0, message: 'Ready to upload' };
    
    const response = await fetch(`/progress/${uploadId}`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'include'
    });

    if (!response.ok) {
        throw new Error(`Progress fetch failed: ${response.status}`);
    }

    return await response.json();
}

/**
 * Update progress UI with latest status
 */
function updateProgressUI(progressData) {
    const progressBar = document.querySelector('.progress-bar');
    const progressMessage = document.getElementById('progressMessage');
    
    if (!progressBar || !progressMessage) return;
    
    // Update progress bar
    const percentage = typeof progressData.status === 'number' 
        ? progressData.status 
        : parseFloat(progressData.status) || 0;
    
    progressBar.style.width = `${percentage}%`;
    progressBar.setAttribute('aria-valuenow', percentage);
    
    // Update message
    updateProgressMessage(progressData.message || `Processing ${percentage.toFixed(1)}%`);
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
        : 'var(--text-secondary)';
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
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    });
}

/**
 * Set theme and update icon
 */
function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    
    // Update icon
    const icon = document.querySelector('.theme-toggle i');
    if (icon) {
        icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
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
        navToggle.setAttribute('aria-expanded', 
            navToggle.getAttribute('aria-expanded') === 'true' ? 'false' : 'true'
        );
    });
    
    // Close menu when clicking outside
    document.addEventListener('click', (event) => {
        if (navMenu.classList.contains('active') && 
            !navMenu.contains(event.target) && 
            !navToggle.contains(event.target)) {
            
            navMenu.classList.remove('active');
            navToggle.setAttribute('aria-expanded', 'false');
        }
    });
}

/**
 * Tab Switching between Upload and Link options
 */
function initTabSwitching() {
    const tabs = document.querySelectorAll('.tab-btn');
    if (!tabs.length) return;
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.getAttribute('data-tab');
            if (!target) return;
            
            // Remove active class from all tabs and contents
            document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            // Add active class to current tab and content
            tab.classList.add('active');
            
            const content = document.getElementById(`${target}-tab`);
            if (content) content.classList.add('active');
        });
    });
    
    // Activate first tab by default if none is active
    if (!document.querySelector('.tab-btn.active') && tabs.length > 0) {
        tabs[0].click();
    }
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
                uploadArea.classList.add('highlight');
            });
        });
        
        // Remove highlighting when drag ends
        ['dragleave', 'drop'].forEach(event => {
            uploadArea.addEventListener(event, () => {
                uploadArea.classList.remove('highlight');
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
        
        // Submit the form
        const formData = new FormData(uploadForm);
        submitFormWithProgress(uploadForm.action, formData);
    });
    
    
    // Handle file selection
    function handleFileSelection(file) {
        // Validate file type
        const validTypes = ['audio/mpeg', 'audio/wav', 'video/mp4', 'audio/m4a'];
        if (!validTypes.includes(file.type)) {
            updateProgressMessage('Please upload a valid audio or video file.', true);
            showProgressContainer();
            return;
        }
        
        // Update UI with file info
        if (fileInfo) {
            const fileName = fileInfo.querySelector('.file-name');
            if (fileName) {
                fileName.textContent = file.name;
                fileInfo.classList.remove('hidden');
            }
        }
        
        // Reset progress UI
        resetProgressUI();
    }
    
    // Reset progress UI
    function resetProgressUI() {
        showProgressContainer();
        if (progressBar) progressBar.style.width = '0%';
        updateProgressMessage('');
    }
    
    // Show progress container
    function showProgressContainer() {
        if (progressContainer) {
            progressContainer.classList.remove('hidden');
        }
    }
}

/**
 * Smooth Scrolling for anchor links
 */
function initSmoothScrolling() {
    document.querySelectorAll('a[href^="#"]:not([href="#"])').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

/**
 * Animations with Intersection Observer API
 */
function initAnimations() {
    if (!('IntersectionObserver' in window)) return;
    
    const fadeInElements = document.querySelectorAll(
        '.feature-card, .step-card, .hero-title, .hero-subtitle, .upload-container'
    );
    
    if (fadeInElements.length === 0) return;
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('fade-in');
                observer.unobserve(entry.target);
            }
        });
    }, {
        root: null,
        rootMargin: '0px',
        threshold: 0.1
    });
    
    fadeInElements.forEach(element => observer.observe(element));
}
