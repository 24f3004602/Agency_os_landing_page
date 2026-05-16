/* ============================================
   AGENCYOS — JAVASCRIPT
   Sticky Navbar · Mobile Menu · Globe · Carousel
   ============================================ */

document.addEventListener('DOMContentLoaded', () => {
    initializeNavbar();
    initializePremiumScroll();
    initializeScrollAnimations();
    initializeInteractions();
    initializeCounters();
    initializeFeaturesCarousel();
    console.log('🚀 AgencyOS loaded');
});

// ============================================
// NAVBAR — Sticky, always visible, mobile-aware
// ============================================

function initializeNavbar() {
    const navbar   = document.getElementById('mainNavbar');
    const hamburger = document.getElementById('hamburger');
    const navMenu  = document.getElementById('navMenu');
    const navLinks = document.querySelectorAll('.nav-link');

    if (!navbar) return;

    // ------- Scroll: add .scrolled class -------
    const onScroll = () => {
        if (window.scrollY > 40) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }

        // Scroll progress bar (CSS var used in navbar::after)
        const scrollTop  = document.documentElement.scrollTop;
        const docHeight  = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        const pct        = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
        document.documentElement.style.setProperty('--scroll-percent', `${pct}%`);

        updateActiveNavLink();
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll(); // run once on load

    // ------- Hamburger toggle -------
    if (hamburger && navMenu) {
        hamburger.addEventListener('click', () => {
            const open = navMenu.classList.toggle('active');
            hamburger.classList.toggle('active', open);
            hamburger.setAttribute('aria-expanded', open);
            navMenu.setAttribute('aria-hidden', !open);
        });

        // Close menu when a link is clicked
        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                navMenu.classList.remove('active');
                hamburger.classList.remove('active');
                hamburger.setAttribute('aria-expanded', 'false');
                navMenu.setAttribute('aria-hidden', 'true');
            });
        });

        // Close menu on outside click
        document.addEventListener('click', (e) => {
            if (!navbar.contains(e.target)) {
                navMenu.classList.remove('active');
                hamburger.classList.remove('active');
                hamburger.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // ------- Smooth scroll for nav links -------
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            if (href && href.startsWith('#')) {
                e.preventDefault();
                scrollToSection(href.substring(1));
            }
        });
    });

    // ------- Close mobile menu on resize -------
    window.addEventListener('resize', () => {
        if (window.innerWidth > 768 && navMenu && hamburger) {
            navMenu.classList.remove('active');
            hamburger.classList.remove('active');
            hamburger.setAttribute('aria-expanded', 'false');
        }
    });
}

function updateActiveNavLink() {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.nav-link');
    let current    = '';

    sections.forEach(section => {
        if (window.scrollY >= section.offsetTop - 120) {
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
// SMOOTH SCROLL HELPER
// ============================================

function scrollToSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (!section) return;
    const navbarHeight = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--navbar-height')) || 76;
    const top = section.getBoundingClientRect().top + window.scrollY - navbarHeight;
    window.scrollTo({ top, behavior: 'smooth' });
}

// Expose globally (called from HTML onclick)
window.scrollToSection = scrollToSection;

// ============================================
// SMOOTH SCROLL (Lenis)
// ============================================

function initializePremiumScroll() {
    if (typeof Lenis !== 'undefined') {
        const lenis = new Lenis({
            duration: 1.2,
            easing: t => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
            smoothWheel: true,
        });

        const raf = time => { lenis.raf(time); requestAnimationFrame(raf); };
        requestAnimationFrame(raf);
    }

    // Parallax orbs
    let ticking = false;
    window.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(() => {
                const scrolled = window.scrollY;
                document.querySelectorAll('.gradient-orb').forEach((orb, i) => {
                    const speed = 0.15 + i * 0.08;
                    orb.style.transform = `translateY(${scrolled * speed}px)`;
                });
                ticking = false;
            });
            ticking = true;
        }
    }, { passive: true });
}

// ============================================
// SCROLL REVEAL ANIMATIONS
// ============================================

function initializeScrollAnimations() {
    const revealEls = document.querySelectorAll(
        '.ps-item, .feature-carousel-item'
    );

    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('reveal', 'active');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });

    revealEls.forEach(el => {
        el.classList.add('reveal');
        observer.observe(el);
    });
}

// ============================================
// INTERACTIONS
// ============================================

function initializeInteractions() {
    // Cursor glow
    document.addEventListener('mousemove', e => {
        document.body.style.setProperty('--cursor-x', `${e.clientX}px`);
        document.body.style.setProperty('--cursor-y', `${e.clientY}px`);
    });

    // Card mouse-tracking glow
    document.querySelectorAll('.graphic-card').forEach(card => {
        card.addEventListener('mousemove', e => {
            const rect = card.getBoundingClientRect();
            card.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
            card.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);
        });
    });

    // Button ripple + hover lift
    document.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', createRipple);
    });

    // Hero visual parallax (desktop only)
    const heroVisual = document.querySelector('.hero-visual');
    if (heroVisual && window.matchMedia('(min-width: 769px)').matches) {
        window.addEventListener('mousemove', e => {
            const x = (window.innerWidth  / 2 - e.clientX) / 60;
            const y = (window.innerHeight / 2 - e.clientY) / 60;
            heroVisual.style.transform = `translate(${x}px, ${y}px)`;
        });
    }

    // Video play button
    const playBtn = document.querySelector('.video-play-btn');
    if (playBtn) playBtn.addEventListener('click', openVideoModal);

    document.querySelectorAll('[data-close-video-modal]').forEach(el => {
        el.addEventListener('click', closeVideoModal);
    });

    // Scroll indicator
    const scrollInd = document.querySelector('.hero-scroll-indicator');
    if (scrollInd) scrollInd.addEventListener('click', () => scrollToSection('demo'));

    // Initialize hero widgets
    initializeHeroWidgets();
    initializeGlobe();
}

// ============================================
// GLOBE ROTATION
// ============================================

function initializeGlobe() {
    const container = document.getElementById('globeContainer');
    const globe     = document.getElementById('globe');
    if (!container || !globe) return;

    let targetX = 0, targetY = 0;
    let currentX = 0, currentY = 0;
    let autoSpin = 0;

    container.addEventListener('mousemove', e => {
        const rect = container.getBoundingClientRect();
        targetY = ((e.clientX - rect.left - rect.width  / 2) / (rect.width  / 2)) * 14;
        targetX = ((e.clientY - rect.top  - rect.height / 2) / (rect.height / 2)) * -14;
    });

    container.addEventListener('mouseleave', () => { targetX = 0; targetY = 0; });

    const animate = () => {
        currentX += (targetX - currentX) * 0.1;
        currentY += (targetY - currentY) * 0.1;
        autoSpin += 0.28;
        globe.style.transform = `rotateX(${currentX}deg) rotateY(${autoSpin + currentY}deg)`;
        requestAnimationFrame(animate);
    };
    animate();
}

// ============================================
// HERO WIDGETS
// ============================================

function initializeHeroWidgets() {
    // Mini bars
    document.querySelectorAll('.mini-bar').forEach((bar, i) => {
        bar.style.setProperty('--bar-height', `${bar.dataset.height || 60}%`);
        bar.style.setProperty('--index', i);
    });

    // Metric counter
    document.querySelectorAll('.widget-metric[data-count]').forEach(metric => {
        const target = parseInt(metric.dataset.count || '0', 10);
        let start = null;
        const tick = ts => {
            if (!start) start = ts;
            const p = Math.min((ts - start) / 900, 1);
            metric.textContent = Math.floor(p * target);
            if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    });

    // Uptime ring
    const ring  = document.querySelector('.uptime-ring');
    const prog  = document.querySelector('.uptime-progress');
    if (ring && prog) {
        const uptime = parseFloat(ring.dataset.uptime || '99.9');
        const r = 48, circ = 2 * Math.PI * r;
        prog.style.strokeDasharray = `${circ}`;
        requestAnimationFrame(() => {
            prog.style.strokeDashoffset = `${circ * (1 - uptime / 100)}`;
        });
    }
}

// ============================================
// RIPPLE EFFECT
// ============================================

function createRipple(e) {
    const btn  = e.currentTarget;
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x    = e.clientX - rect.left - size / 2;
    const y    = e.clientY - rect.top  - size / 2;

    const ripple = document.createElement('span');
    ripple.style.cssText = `
        position: absolute;
        width: ${size}px; height: ${size}px;
        background: radial-gradient(circle, rgba(255,255,255,0.5), transparent);
        border-radius: 50%;
        left: ${x}px; top: ${y}px;
        pointer-events: none;
        animation: ripple-anim 0.6s ease-out forwards;
    `;

    if (getComputedStyle(btn).position === 'static') btn.style.position = 'relative';
    btn.appendChild(ripple);
    setTimeout(() => ripple.remove(), 600);
}

// Inject ripple keyframe
const rippleStyle = document.createElement('style');
rippleStyle.textContent = `@keyframes ripple-anim { to { transform: scale(4); opacity: 0; } }`;
document.head.appendChild(rippleStyle);

// ============================================
// VIDEO MODAL
// ============================================

function openVideoModal() {
    const modal = document.getElementById('videoModal');
    const frame = document.getElementById('demoVideoFrame');
    if (!modal || !frame) return;
    if (!frame.src || frame.src === 'about:blank') {
        frame.src = frame.dataset.src || '';
    }
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
}

function closeVideoModal() {
    const modal = document.getElementById('videoModal');
    const frame = document.getElementById('demoVideoFrame');
    if (!modal || !frame) return;
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    frame.src = 'about:blank';
    document.body.style.overflow = '';
}

// ============================================
// COUNTER ANIMATION
// ============================================

function initializeCounters() {
    const hero = document.querySelector('.hero');
    if (!hero) return;

    const obs = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) {
            document.querySelectorAll('.hero-stats .counter').forEach((el, i) => {
                setTimeout(() => animateCounter(el), i * 120);
            });
            obs.disconnect();
        }
    }, { threshold: 0.4 });
    obs.observe(hero);
}

function animateCounter(el) {
    const target  = parseInt(el.getAttribute('data-target')) || 0;
    const suffix  = el.getAttribute('data-suffix') || '';
    let current   = 0;
    const inc     = Math.ceil(target / 28);

    const timer = setInterval(() => {
        current += inc;
        if (current >= target) {
            el.textContent = target + suffix;
            clearInterval(timer);
        } else {
            el.textContent = current + suffix;
        }
    }, 30);
}

// ============================================
// FEATURES CAROUSEL
// ============================================

function initializeFeaturesCarousel() {
    const carousel = document.querySelector('[data-carousel]');
    if (!carousel) return;

    const track      = carousel.querySelector('.features-carousel-track');
    const items      = Array.from(carousel.querySelectorAll('.feature-carousel-item'));
    const prevBtn    = carousel.querySelector('[data-carousel-prev]');
    const nextBtn    = carousel.querySelector('[data-carousel-next]');
    const indicators = Array.from(document.querySelectorAll('[data-carousel-indicators] .carousel-dot'));

    if (!track || !items.length) return;

    const ORIG       = items.length;
    let visibleCount = getVisibleCount();
    let maxIndex     = Math.max(ORIG - visibleCount, 0);
    let current      = 0;
    let animating    = false;

    function getVisibleCount() {
        if (window.innerWidth <= 768) return 1;
        if (window.innerWidth <= 1100) return 2;
        return 3;
    }

    function stepPx() {
        if (!items.length) return 0;
        const w   = items[0].getBoundingClientRect().width;
        const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
        return w + gap;
    }

    function update(smooth = true) {
        track.style.transition = smooth
            ? 'transform 0.85s cubic-bezier(0.22, 1, 0.36, 1)'
            : 'none';
        track.style.transform = `translateX(-${current * stepPx()}px)`;

        items.forEach((item, i) => {
            item.classList.toggle('active', i >= current && i < current + visibleCount);
        });

        indicators.forEach((dot, i) => dot.classList.toggle('is-active', i === current));

        if (prevBtn) prevBtn.disabled = current <= 0;
        if (nextBtn) nextBtn.disabled = current >= maxIndex;
    }

    function go(index) {
        if (animating) return;
        current   = Math.min(Math.max(index, 0), maxIndex);
        animating = true;
        update(true);
        setTimeout(() => { animating = false; }, 900);
    }

    if (nextBtn) nextBtn.addEventListener('click', () => go(current + 1));
    if (prevBtn) prevBtn.addEventListener('click', () => go(current - 1));
    indicators.forEach((dot, i) => dot.addEventListener('click', () => go(i)));

    // Keyboard
    document.addEventListener('keydown', e => {
        if (carousel.offsetParent === null) return;
        if (e.key === 'ArrowLeft')  { e.preventDefault(); go(current - 1); }
        if (e.key === 'ArrowRight') { e.preventDefault(); go(current + 1); }
    });

    // Resize
    window.addEventListener('resize', () => {
        visibleCount = getVisibleCount();
        maxIndex     = Math.max(ORIG - visibleCount, 0);
        current      = Math.min(current, maxIndex);
        update(false);
    });

    update(false);
}

// ============================================
// KEYBOARD ACCESSIBILITY
// ============================================

document.addEventListener('keydown', e => {
    if (e.key === 'Tab')    document.body.classList.add('keyboard-nav');
    if (e.key === 'Escape') closeVideoModal();
});
document.addEventListener('mousedown', () => document.body.classList.remove('keyboard-nav'));

// ============================================
// LAZY IMAGE LOADING
// ============================================

if ('IntersectionObserver' in window) {
    const imgObs = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                if (img.dataset.src) { img.src = img.dataset.src; imgObs.unobserve(img); }
            }
        });
    });
    document.querySelectorAll('img[data-src]').forEach(img => imgObs.observe(img));
}

console.log('%c🎨 AgencyOS Design System', 'color:#EB5E28;font-size:16px;font-weight:bold;');