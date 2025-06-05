// Common JavaScript functionality for SubTranscribe application

// Initialize particles background
function initParticlesBackground() {
    const particlesContainer = document.getElementById('particles-background');
    if (!particlesContainer) return;
    
    const numParticles = Math.min(window.innerWidth / 10, 100); // Responsive number of particles
    const particles = [];
    const colors = [
        ['#60a5fa', '#3b82f6'], // Primary blue
        ['#a78bfa', '#8b5cf6'], // Secondary purple
        ['#34d399', '#10b981'], // Green
        ['#f472b6', '#ec4899'], // Pink
    ];
    
    // Create particles
    for (let i = 0; i < numParticles; i++) {
        const particle = document.createElement('div');
        particle.classList.add('particle');
        
        // Random properties
        const size = Math.random() * 10 + 5;
        const colorPair = colors[Math.floor(Math.random() * colors.length)];
        
        // Set particle position and size
        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        particle.style.left = `${Math.random() * 100}%`;
        particle.style.top = `${Math.random() * 100}%`;
        particle.style.opacity = Math.random() * 0.5 + 0.1;
        
        // Set custom properties for colors
        particle.style.setProperty('--particle-color-start', colorPair[0]);
        particle.style.setProperty('--particle-color-end', colorPair[1]);
        
        // Add to container
        particlesContainer.appendChild(particle);
        
        // Store particle data for animation
        particles.push({
            element: particle,
            size: size,
            x: parseFloat(particle.style.left),
            y: parseFloat(particle.style.top),
            speedX: Math.random() * 0.2 - 0.1,
            speedY: Math.random() * 0.2 - 0.1,
            maxDistance: 120 // Max distance to react to mouse/touch
        });
    }
    
    // Animation loop
    function animateParticles() {
        particles.forEach(particle => {
            // Update position
            particle.x += particle.speedX;
            particle.y += particle.speedY;
            
            // Boundary check
            if (particle.x < 0) particle.x = 100;
            if (particle.x > 100) particle.x = 0;
            if (particle.y < 0) particle.y = 100;
            if (particle.y > 100) particle.y = 0;
            
            // Apply position
            particle.element.style.left = `${particle.x}%`;
            particle.element.style.top = `${particle.y}%`;
        });
        
        requestAnimationFrame(animateParticles);
    }
    
    // Start animation
    animateParticles();
}

// Initialize common elements when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize AOS animations if AOS is available
    if (typeof AOS !== 'undefined') {
        AOS.init({
            once: true,
            duration: 800,
            offset: 100,
            delay: 100,
            easing: 'ease-out'
        });
    }
    
    // Initialize particles background
    initParticlesBackground();
}); 