/* ============================================
   PREMIUM AGENCYOS - ADVANCED JAVASCRIPT
   Sophisticated Interactions & Animations
   ============================================ */

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initializePremiumScroll();
    initializeNavbar();
    initializeScrollAnimations();
    initializeInteractions();
    initializeCounters();
    initializeROICalculator();
    initializeWorkflow();
    initializeFeaturesCarousel();
    console.log('🚀 Premium AgencyOS loaded');
});

// ============================================
// PREMIUM SCROLL EFFECTS
// ============================================

function initializePremiumScroll() {
    // Initialize Lenis for smooth scroll
    if (typeof Lenis !== 'undefined') {
        const lenis = new Lenis({
            duration: 1.2,
            easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
            smoothWheel: true,
            smoothTouch: true,
            touchMultiplier: 2,
        });

        function raf(time) {
            lenis.raf(time);
            requestAnimationFrame(raf);
        }

        requestAnimationFrame(raf);
    }

    // Parallax effect for gradient orbs
    let ticking = false;
    window.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(() => {
                const scrolled = window.scrollY;
                document.querySelectorAll('.gradient-orb').forEach((orb, index) => {
                    const speed = 0.2 + index * 0.1;
                    orb.style.transform = `translateY(${scrolled * speed}px)`;
                });
                ticking = false;
            });
            ticking = true;
        }
    });

    // Reveal animations on scroll
    const reveals = document.querySelectorAll(
        '.metric-card, .ps-item, ' +
        '.workflow-item, .process-step, ' +
        '.feature-carousel-item'
    );

    const revealObserver = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('reveal', 'active');
                revealObserver.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.15,
        rootMargin: '0px 0px -80px 0px'
    });

    reveals.forEach(el => {
        el.classList.add('reveal');
        revealObserver.observe(el);
    });

    // Dynamic navbar blur on scroll
    const navbar = document.querySelector('.navbar-content');
    if (navbar) {
        window.addEventListener('scroll', () => {
            const scroll = window.scrollY;
            const blurAmount = Math.min(25, 10 + scroll * 0.015);
            navbar.style.backdropFilter = `blur(${blurAmount}px)`;
            navbar.style.borderColor = `rgba(235, 94, 40, ${Math.min(0.3, 0.05 + scroll * 0.0003)})`;
        }, { passive: true });
    }

    // Magnetic scrolling sections
    const sections = document.querySelectorAll('section');
    window.addEventListener('scroll', () => {
        sections.forEach(section => {
            const rect = section.getBoundingClientRect();
            const offset = rect.top * -0.02;
            section.style.transform = `translateY(${offset}px)`;
        });
    }, { passive: true });
}

// ============================================
// NAVBAR INTERACTIONS
// ============================================

function initializeNavbar() {
    const navbar = document.querySelector('.navbar-content');
    const hamburger = document.querySelector('.hamburger');
    const navMenu = document.querySelector('.nav-menu');
    const navLinks = document.querySelectorAll('.nav-link');

    let lastScrollTop = 0;

    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

        if (scrollTop > 50) {
            navbar.style.background = 'linear-gradient(135deg, rgba(37, 36, 34, 0.85) 0%, rgba(64, 61, 57, 0.65) 100%)';
            navbar.style.boxShadow = '0 12px 40px rgba(235, 94, 40, 0.15)';
        } else {
            navbar.style.background = 'linear-gradient(135deg, rgba(37, 36, 34, 0.7) 0%, rgba(64, 61, 57, 0.5) 100%)';
            navbar.style.boxShadow = '0 8px 32px rgba(0, 0, 0, 0.4)';
        }

        lastScrollTop = scrollTop <= 0 ? 0 : scrollTop;
    });

    // Mobile menu toggle
    if (hamburger) {
        hamburger.addEventListener('click', () => {
            hamburger.classList.toggle('active');
            navMenu.classList.toggle('active');
        });

        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                hamburger.classList.remove('active');
                navMenu.classList.remove('active');
            });
        });
    }

    // Smooth scroll for nav links
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            if (href.startsWith('#')) {
                e.preventDefault();
                scrollToSection(href.substring(1));
            }
        });
    });

    // Update active nav link on scroll
    updateActiveNavLink();
    window.addEventListener('scroll', updateActiveNavLink);
}

function updateActiveNavLink() {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.nav-link');
    let current = '';

    sections.forEach(section => {
        const sectionTop = section.offsetTop;
        const sectionHeight = section.clientHeight;
        if (scrollY >= sectionTop - 200) {
            current = section.getAttribute('id');
        }
    });

    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === `#${current}`) {
            link.classList.add('active');
        }
    });
}

// ============================================
// SCROLL ANIMATIONS
// ============================================

function initializeScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -100px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.classList.add('animate-in');
                }, index * 50);
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observe all animatable elements
    const elements = document.querySelectorAll(
        '.hero-badge, .hero-title, .hero-description, .hero-ctas, .hero-stats, ' +
        '.metric-card, .company-logo, .ps-item, ' +
        '.workflow-item, .process-step'
    );

    elements.forEach(el => {
        observer.observe(el);
    });

    // Add animation styles
    const style = document.createElement('style');
    style.textContent = `
        [class*="animate-"] {
            animation: fadeInUp 0.6s ease-out forwards;
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    `;
    document.head.appendChild(style);
}

// ============================================
// SMOOTH SCROLL
// ============================================

function scrollToSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        const offset = 80;
        const sectionTop = section.offsetTop - offset;
        
        window.scrollTo({
            top: sectionTop,
            behavior: 'smooth'
        });
    }
}

// ============================================
// INTERACTIVE EFFECTS
// ============================================

function initializeInteractions() {
    // Button ripple effect
    const buttons = document.querySelectorAll('button');
    buttons.forEach(button => {
        button.addEventListener('click', (e) => {
            createRipple(e);
        });

        button.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px)';
        });

        button.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });

    document.addEventListener('mousemove', (e) => {
        document.body.style.setProperty('--cursor-x', `${e.clientX}px`);
        document.body.style.setProperty('--cursor-y', `${e.clientY}px`);
    });

    // Interactive cards
    const interactiveCards = document.querySelectorAll(
        '.metric-card, .graphic-card'
    );
    
    interactiveCards.forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            card.style.setProperty('--mouse-x', `${x}px`);
            card.style.setProperty('--mouse-y', `${y}px`);
        });
    });

    // Parallax effect for hero visual
    const heroVisual = document.querySelector('.hero-visual');
    if (heroVisual) {
        window.addEventListener('mousemove', (e) => {
            const x = (window.innerWidth / 2 - e.clientX) / 50;
            const y = (window.innerHeight / 2 - e.clientY) / 50;
            heroVisual.style.transform = `translate(${x}px, ${y}px)`;
        });
    }

    // Video play button interaction
    const videoPlayBtn = document.querySelector('.video-play-btn');
    if (videoPlayBtn) {
        videoPlayBtn.addEventListener('click', handleVideoClick);
    }

    const closeVideoModalElements = document.querySelectorAll('[data-close-video-modal]');
    closeVideoModalElements.forEach((element) => {
        element.addEventListener('click', closeVideoModal);
    });

    initializeHeroWidgets();
    initializeGlobe();
}

// ============================================
// GLOBE INTERACTIONS
// ============================================

function initializeGlobe() {
    const globeContainer = document.getElementById('globeContainer');
    const globe = document.getElementById('globe');
    
    if (!globeContainer || !globe) return;

    let mouseX = 0;
    let mouseY = 0;
    let targetRotateX = 0;
    let targetRotateY = 0;
    let currentRotateX = 0;
    let currentRotateY = 0;
    let autoSpin = 0;

    // Track mouse movement over globe container
    globeContainer.addEventListener('mousemove', (e) => {
        const rect = globeContainer.getBoundingClientRect();
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        mouseX = e.clientX - rect.left;
        mouseY = e.clientY - rect.top;

        // Calculate rotation based on mouse position
        targetRotateY = ((mouseX - centerX) / centerX) * 15;
        targetRotateX = ((mouseY - centerY) / centerY) * -15;
    });

    // Reset on mouse leave
    globeContainer.addEventListener('mouseleave', () => {
        targetRotateX = 0;
        targetRotateY = 0;
    });

    // Smooth animation loop for rotation
    function animateGlobe() {
        currentRotateX += (targetRotateX - currentRotateX) * 0.1;
        currentRotateY += (targetRotateY - currentRotateY) * 0.1;
        autoSpin += 0.3;

        globe.style.transform = `rotateX(${currentRotateX}deg) rotateY(${autoSpin + currentRotateY}deg)`;
        requestAnimationFrame(animateGlobe);
    }

    animateGlobe();
}

function createRipple(e) {
    const button = e.currentTarget;
    const ripple = document.createElement('span');
    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = e.clientX - rect.left - size / 2;
    const y = e.clientY - rect.top - size / 2;

    ripple.style.cssText = `
        position: absolute;
        width: ${size}px;
        height: ${size}px;
        background: radial-gradient(circle, rgba(255,255,255,0.6), transparent);
        border-radius: 50%;
        left: ${x}px;
        top: ${y}px;
        pointer-events: none;
        animation: ripple-animation 0.6s ease-out;
    `;

    // Ensure button has position relative
    if (getComputedStyle(button).position === 'static') {
        button.style.position = 'relative';
    }

    button.appendChild(ripple);
    setTimeout(() => ripple.remove(), 600);
}

function initializeHeroWidgets() {
    const bars = document.querySelectorAll('.mini-bar');
    bars.forEach((bar, index) => {
        const targetHeight = bar.dataset.height || '60';
        bar.style.setProperty('--bar-height', `${targetHeight}%`);
        bar.style.setProperty('--index', index);
    });

    const metrics = document.querySelectorAll('.widget-metric[data-count]');
    metrics.forEach((metric) => {
        const target = parseInt(metric.dataset.count || '0', 10);
        const duration = 1000;
        let start = null;

        function tick(timestamp) {
            if (!start) start = timestamp;
            const progress = Math.min((timestamp - start) / duration, 1);
            metric.textContent = Math.floor(progress * target).toString();
            if (progress < 1) {
                requestAnimationFrame(tick);
            }
        }

        requestAnimationFrame(tick);
    });

    const uptimeProgress = document.querySelector('.uptime-progress');
    const uptimeRing = document.querySelector('.uptime-ring');
    if (uptimeProgress && uptimeRing) {
        const uptime = parseFloat(uptimeRing.dataset.uptime || '99.9');
        const radius = 48;
        const circumference = 2 * Math.PI * radius;
        const offset = circumference * (1 - uptime / 100);

        uptimeProgress.style.strokeDasharray = `${circumference}`;
        requestAnimationFrame(() => {
            uptimeProgress.style.strokeDashoffset = `${offset}`;
        });
    }
}

// ============================================
// COUNTER ANIMATION
// ============================================

function initializeCounters() {
    // Hero stats counters
    const heroSection = document.querySelector('.hero');
    if (heroSection) {
        const heroObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const heroCounters = document.querySelectorAll('.hero-stats .counter');
                    heroCounters.forEach((el, index) => {
                        setTimeout(() => {
                            animateCounter(el);
                        }, index * 100);
                    });
                    heroObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });
        heroObserver.observe(heroSection);
    }

    // Metrics showcase counters
    const metricsSection = document.querySelector('.metrics-showcase');
    if (metricsSection) {
        const metricsObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const metricCounters = document.querySelectorAll('.metrics-showcase .metric-number');
                    metricCounters.forEach((el, index) => {
                        setTimeout(() => {
                            animateCounter(el);
                        }, index * 100);
                    });
                    metricsObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });
        metricsObserver.observe(metricsSection);
    }

    // Case study counters
    const caseStudiesSection = document.querySelector('.case-studies');
    if (caseStudiesSection) {
        const caseObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const caseCounters = document.querySelectorAll('.cases-grid .counter');
                    caseCounters.forEach((el, index) => {
                        setTimeout(() => {
                            animateCounter(el);
                        }, index * 100);
                    });
                    caseObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });
        caseObserver.observe(caseStudiesSection);
    }
}

function animateCounter(element) {
    const target = parseInt(element.getAttribute('data-target')) || 0;
    const suffix = element.getAttribute('data-suffix') || '';
    let current = 0;
    const increment = Math.ceil(target / 30);
    
    const counter = setInterval(() => {
        current += increment;
        
        if (current >= target) {
            element.textContent = String(target).padStart(2, '0') + suffix;
            clearInterval(counter);
        } else {
            element.textContent = String(current).padStart(2, '0') + suffix;
        }
    }, 30);
}


// ============================================
// VIDEO INTERACTION
// ============================================

function handleVideoClick() {
    const videoModal = document.getElementById('videoModal');
    const demoVideoFrame = document.getElementById('demoVideoFrame');
    if (!videoModal || !demoVideoFrame) return;

    if (!demoVideoFrame.src) {
        demoVideoFrame.src = demoVideoFrame.dataset.src || '';
    }

    videoModal.classList.add('active');
    videoModal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
}

function closeVideoModal() {
    const videoModal = document.getElementById('videoModal');
    const demoVideoFrame = document.getElementById('demoVideoFrame');
    if (!videoModal || !demoVideoFrame) return;

    videoModal.classList.remove('active');
    videoModal.setAttribute('aria-hidden', 'true');
    demoVideoFrame.src = '';
    document.body.style.overflow = '';
}

// ============================================
// SCROLL PROGRESS INDICATOR
// ============================================

window.addEventListener('scroll', () => {
    const scrollTop = document.documentElement.scrollTop;
    const docHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
    const scrollPercent = (scrollTop / docHeight) * 100;

    // Can be used to update a progress bar if added to HTML
    document.documentElement.style.setProperty('--scroll-percent', `${scrollPercent}%`);
});

// ============================================
// KEYBOARD NAVIGATION
// ============================================

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const hamburger = document.querySelector('.hamburger');
        const navMenu = document.querySelector('.nav-menu');
        
        if (hamburger && hamburger.classList.contains('active')) {
            hamburger.classList.remove('active');
            navMenu.classList.remove('active');
        }

        closeVideoModal();
    }
});

// ============================================
// HERO SCROLL INDICATOR
// ============================================

const scrollIndicator = document.querySelector('.hero-scroll-indicator');
if (scrollIndicator) {
    scrollIndicator.addEventListener('click', () => {
        scrollToSection('demo');
    });
}


// ============================================
// WINDOW RESIZE HANDLER
// ============================================

window.addEventListener('resize', () => {
    if (window.innerWidth > 768) {
        const navMenu = document.querySelector('.nav-menu');
        const hamburger = document.querySelector('.hamburger');
        if (navMenu && hamburger) {
            navMenu.classList.remove('active');
            hamburger.classList.remove('active');
        }
    }
});

// ============================================
// PERFORMANCE OPTIMIZATION - Lazy Loading
// ============================================

if ('IntersectionObserver' in window) {
    const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                if (img.dataset.src) {
                    img.src = img.dataset.src;
                    img.removeAttribute('data-src');
                    imageObserver.unobserve(img);
                }
            }
        });
    });

    document.querySelectorAll('img[data-src]').forEach(img => {
        imageObserver.observe(img);
    });
}

// ============================================
// MOUSE FOLLOW LIGHT EFFECT (Optional Enhancement)
// ============================================


// ============================================
// ROI CALCULATOR
// ============================================

function initializeROICalculator() {
    const teamSizeSlider = document.getElementById('teamSizeSlider');
    const hourlyRateSlider = document.getElementById('hourlyRateSlider');
    const teamSizeValue = document.getElementById('teamSizeValue');
    const hourlyRateValue = document.getElementById('hourlyRateValue');
    const roiAmount = document.getElementById('roiAmount');
    const roiFormula = document.getElementById('roiFormula');
    const roiButtonAmount = document.getElementById('roiButtonAmount');

    function calculateROI() {
        const teamSize = parseInt(teamSizeSlider.value);
        const hourlyRate = parseInt(hourlyRateSlider.value);
        const hoursPerMonth = 160;
        const timeSaved = 0.30; // 30%
        
        const monthlySavings = Math.round(teamSize * hourlyRate * hoursPerMonth * timeSaved);
        
        // Update display values
        teamSizeValue.textContent = teamSize;
        hourlyRateValue.textContent = hourlyRate;
        roiAmount.textContent = monthlySavings.toLocaleString();
        roiButtonAmount.textContent = monthlySavings.toLocaleString();
        
        // Update formula
        const yearlySavings = monthlySavings * 12;
        roiFormula.textContent = `${teamSize} people × $${hourlyRate}/hr × ${hoursPerMonth} hrs × 30% = $${monthlySavings.toLocaleString()}/month ($${yearlySavings.toLocaleString()}/year)`;
    }

    if (teamSizeSlider && hourlyRateSlider) {
        // Initial calculation
        calculateROI();
        
        // Update on slider change
        teamSizeSlider.addEventListener('input', calculateROI);
        hourlyRateSlider.addEventListener('input', calculateROI);
    }
}

// ============================================
// WORKFLOW INTERACTIONS
// ============================================
function initializeWorkflow() {
    const workflowItems = document.querySelectorAll('.workflow-item');

    workflowItems.forEach((item) => {
        item.addEventListener('click', () => {
            const detail = item.querySelector('.workflow-detail');
            if (detail) {
                detail.classList.toggle('expanded');
                item.setAttribute('aria-expanded', detail.classList.contains('expanded'));
            }
        });

        // Keyboard support
        item.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                item.click();
            }
        });
    });
}

// ============================================
// FEATURES CAROUSEL
// ============================================

function initializeFeaturesCarousel() {
    const carousel = document.querySelector('[data-carousel]');
    if (!carousel) return;

    const track = carousel.querySelector('.features-carousel-track');
    let items = Array.from(carousel.querySelectorAll('.feature-carousel-item'));
    const prevBtn = carousel.querySelector('[data-carousel-prev]');
    const nextBtn = carousel.querySelector('[data-carousel-next]');
    const indicators = document.querySelectorAll('[data-carousel-indicators] .carousel-dot');

    if (!track || items.length === 0) return;

    const ORIGINAL_COUNT = items.length;
    const VISIBLE_COUNT = 3;
    const MAX_INDEX = Math.max(ORIGINAL_COUNT - VISIBLE_COUNT, 0);
    let currentIndex = 0;
    let isAnimating = false;

    function measureSlideStep() {
        if (!items.length) return 0;

        const itemWidth = items[0].getBoundingClientRect().width;
        const trackStyles = window.getComputedStyle(track);
        const gap = parseFloat(trackStyles.columnGap || trackStyles.gap || '0') || 0;

        return itemWidth + gap;
    }

    function setControlState() {
        if (prevBtn) prevBtn.disabled = currentIndex <= 0;
        if (nextBtn) nextBtn.disabled = currentIndex >= MAX_INDEX;
    }

    function updateCarouselPosition(smooth = true) {
        const step = measureSlideStep();
        if (!step) return;

        if (smooth) {
            track.style.transition = 'transform 0.9s cubic-bezier(0.22, 1, 0.36, 1)';
        } else {
            track.style.transition = 'none';
        }

        track.style.transform = `translateX(-${currentIndex * step}px)`;
        updateIndicators();
        updateItemStates();
        setControlState();
    }

    function updateItemStates() {
        items.forEach((item, idx) => {
            const isVisible = idx >= currentIndex && idx < currentIndex + VISIBLE_COUNT;
            item.classList.toggle('active', isVisible);
        });
    }

    function updateIndicators() {
        indicators.forEach((dot, idx) => {
            dot.classList.toggle('is-active', idx === currentIndex);
        });
    }

    function clampIndex(index) {
        return Math.min(Math.max(index, 0), MAX_INDEX);
    }

    function goToSlide(index) {
        if (isAnimating) return;
        isAnimating = true;

        currentIndex = clampIndex(index);
        updateCarouselPosition(true);

        setTimeout(() => {
            isAnimating = false;
            updateCarouselPosition(false);
        }, 900);
    }

    function nextSlide() {
        if (isAnimating || currentIndex >= MAX_INDEX) return;
        isAnimating = true;

        currentIndex++;
        updateCarouselPosition(true);

        setTimeout(() => {
            isAnimating = false;
            updateCarouselPosition(false);
        }, 900);
    }

    function prevSlide() {
        if (isAnimating || currentIndex <= 0) return;
        isAnimating = true;

        currentIndex--;
        updateCarouselPosition(true);

        setTimeout(() => {
            isAnimating = false;
            updateCarouselPosition(false);
        }, 900);
    }

    // Event listeners
    if (nextBtn) nextBtn.addEventListener('click', nextSlide);
    if (prevBtn) prevBtn.addEventListener('click', prevSlide);

    indicators.forEach((dot, idx) => {
        dot.addEventListener('click', () => goToSlide(idx));
    });

    // Carousel momentum and hover effects
    carousel.addEventListener('mouseenter', () => {
        track.style.cursor = 'grab';
    });

    carousel.addEventListener('mouseleave', () => {
        track.style.cursor = 'auto';
    });

    // Netflix-style item hover effects
    items.forEach((item, idx) => {
        item.addEventListener('mouseenter', () => {
            // Add visual feedback on hover
            item.style.filter = 'brightness(1.15)';
        });

        item.addEventListener('mouseleave', () => {
            item.style.filter = 'brightness(1)';
        });

        // Click to select card
        item.addEventListener('click', () => {
            goToSlide(idx);
        });
    });

    // Keyboard arrow key support with smooth animation
    document.addEventListener('keydown', (e) => {
        if (carousel.offsetParent === null) return;
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            prevSlide();
        }
        if (e.key === 'ArrowRight') {
            e.preventDefault();
            nextSlide();
        }
    });

    window.addEventListener('resize', () => {
        updateCarouselPosition(false);
    });

    // Initialize
    updateCarouselPosition(false); // Start without animation
}

// ============================================
// ACCESSIBILITY - Focus Management
// ============================================

document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
        document.body.classList.add('keyboard-nav');
    }
});

document.addEventListener('mousedown', () => {
    document.body.classList.remove('keyboard-nav');
});

// ============================================
// ANALYTICS & DEBUG INFO
// ============================================

console.log('%c🎨 Premium AgencyOS Design System Loaded', 'color: #EB5E28; font-size: 16px; font-weight: bold;');
console.log('%cTech Stack: HTML5 • CSS3 • Vanilla JS', 'color: #CCC5B9; font-size: 14px;');
console.log('%cDesign: Glassmorphism • Modern Gradients • Smooth Animations', 'color: #CCC5B9; font-size: 14px;');

// Performance metrics
window.addEventListener('load', () => {
    const perfData = window.performance.timing;
    const pageLoadTime = perfData.loadEventEnd - perfData.navigationStart;
    console.log(`%c⚡ Page Load Time: ${pageLoadTime}ms`, 'color: #EB5E28; font-weight: bold;');
});

// ============================================
// UTILITY FUNCTIONS
// ============================================

// Debounce function for performance
function debounce(func, delay) {
    let timeoutId;
    return function(...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
}
// Throttle function for scroll events
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Add CSS for ripple animation
const rippleStyle = document.createElement('style');
rippleStyle.textContent = `
    @keyframes ripple-animation {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
`;
document.head.appendChild(rippleStyle);
