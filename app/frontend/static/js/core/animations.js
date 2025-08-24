// Advanced Animations and Effects System - PERFORMANCE OPTIMIZED

class AnimationManager {
    constructor() {
        this.observers = new Map();
        this.isInitialized = false;
        this.debounceTimer = null;
        this.throttleTimer = null;
        this.init();
    }

    init() {
        if (this.isInitialized) return;
        
        // Use requestIdleCallback for non-critical initialization
        if ('requestIdleCallback' in window) {
            requestIdleCallback(() => {
                this.setupIntersectionObserver();
                this.setupScrollEffects();
                this.setupHoverEffects();
                this.setupParallaxEffects();
                this.setupLoadingAnimations();
                this.isInitialized = true;
            });
        } else {
            // Fallback for older browsers
            setTimeout(() => {
                this.setupIntersectionObserver();
                this.setupScrollEffects();
                this.setupHoverEffects();
                this.setupParallaxEffects();
                this.setupLoadingAnimations();
                this.isInitialized = true;
            }, 100);
        }
    }

    // Intersection Observer for scroll animations - PERFORMANCE OPTIMIZED
    setupIntersectionObserver() {
        if (!('IntersectionObserver' in window)) return;

        const options = {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // Use requestAnimationFrame for smooth animations
                    requestAnimationFrame(() => {
                        entry.target.classList.add('animate-fade-in');
                    });
                    observer.unobserve(entry.target);
                }
            });
        }, options);

        // Use querySelectorAll with specific selectors for better performance
        const animatedElements = document.querySelectorAll('.animate-on-scroll');
        animatedElements.forEach(el => {
            observer.observe(el);
        });
    }

    // Scroll-based effects - PERFORMANCE OPTIMIZED
    setupScrollEffects() {
        let ticking = false;
        let lastScrollY = window.pageYOffset;

        const updateScrollEffects = () => {
            const scrolled = window.pageYOffset;
            
            // Only update if scroll position changed significantly
            if (Math.abs(scrolled - lastScrollY) < 5) {
                ticking = false;
                return;
            }
            
            lastScrollY = scrolled;
            
            // Use transform3d for GPU acceleration
            const parallaxElements = document.querySelectorAll('.parallax');
            parallaxElements.forEach(element => {
                const speed = element.dataset.speed || 0.5;
                const yPos = -(scrolled * speed);
                element.style.transform = `translate3d(0, ${yPos}px, 0)`;
            });

            // Header background effect
            const header = document.querySelector('nav');
            if (header) {
                if (scrolled > 100) {
                    header.classList.add('scrolled');
                } else {
                    header.classList.remove('scrolled');
                }
            }

            ticking = false;
        };

        // Throttle scroll events for better performance
        window.addEventListener('scroll', () => {
            if (!ticking) {
                requestAnimationFrame(updateScrollEffects);
                ticking = true;
            }
        }, { passive: true });
    }

    // Hover effects - PERFORMANCE OPTIMIZED
    setupHoverEffects() {
        // Use event delegation for better performance
        document.addEventListener('mouseenter', (e) => {
            if (e.target.classList.contains('card')) {
                this.addFloatingEffect(e.target);
            } else if (e.target.classList.contains('btn')) {
                this.addButtonGlow(e.target);
            }
        }, { passive: true });

        document.addEventListener('mouseleave', (e) => {
            if (e.target.classList.contains('card')) {
                this.removeFloatingEffect(e.target);
            } else if (e.target.classList.contains('btn')) {
                this.removeButtonGlow(e.target);
            }
        }, { passive: true });
    }

    // Parallax effects - PERFORMANCE OPTIMIZED
    setupParallaxEffects() {
        const parallaxContainers = document.querySelectorAll('.parallax-container');
        
        parallaxContainers.forEach(container => {
            const elements = container.querySelectorAll('.parallax-element');
            
            elements.forEach((element, index) => {
                // Use transform3d for GPU acceleration
                element.style.transform = `translate3d(0, 0, ${index * -100}px)`;
                element.style.zIndex = elements.length - index;
            });
        });
    }

    // Loading animations - PERFORMANCE OPTIMIZED
    setupLoadingAnimations() {
        // Start animations immediately when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.initializePageAnimations();
            });
        } else {
            this.initializePageAnimations();
        }
    }

    initializePageAnimations() {
        // Add loaded class to body immediately
        document.body.classList.add('loaded');
        
        // Trigger animations for sequence elements
        const animatedElements = document.querySelectorAll('.animate-sequence');
        animatedElements.forEach((el) => {
            // Use requestAnimationFrame for smooth animation
            requestAnimationFrame(() => {
                el.classList.add('loaded');
            });
        });
        
        // Also trigger fade-in animations for other elements
        const fadeInElements = document.querySelectorAll('.animate-fade-in');
        fadeInElements.forEach((el) => {
            requestAnimationFrame(() => {
                el.classList.add('animate-fade-in');
            });
        });
    }

    // Utility methods - PERFORMANCE OPTIMIZED
    addFloatingEffect(element) {
        // Use transform3d for GPU acceleration
        element.style.transform = 'translate3d(0, -8px, 0) scale(1.02)';
        element.style.boxShadow = '0 20px 40px rgba(0,0,0,0.1)';
    }

    removeFloatingEffect(element) {
        element.style.transform = 'translate3d(0, 0, 0) scale(1)';
        element.style.boxShadow = '';
    }

    addButtonGlow(element) {
        element.style.boxShadow = '0 0 20px rgba(102, 126, 234, 0.5)';
        element.style.transform = 'translate3d(0, -2px, 0)';
    }

    removeButtonGlow(element) {
        element.style.boxShadow = '';
        element.style.transform = 'translate3d(0, 0, 0)';
    }

    // Particle system - DISABLED for performance
    createParticleSystem(container, options = {}) {
        // Particle system disabled for performance
        return [];
    }

    createParticle(config) {
        // Particle creation disabled
        return null;
    }

    animateParticle(particle, config) {
        // Particle animation disabled
    }

    // Modal animations - PERFORMANCE OPTIMIZED
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        modal.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Use requestAnimationFrame for smooth animation
        requestAnimationFrame(() => {
            const content = modal.querySelector('.modal-content');
            if (content) {
                content.style.animation = 'modalSlideIn 0.3s ease-out';
            }
        });
    }

    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        const content = modal.querySelector('.modal-content');
        if (content) {
            content.style.animation = 'modalSlideOut 0.3s ease-out';
        }

        setTimeout(() => {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        }, 300);
    }

    // Toast notifications - PERFORMANCE OPTIMIZED
    showToast(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <span class="toast-message">${message}</span>
                <button class="toast-close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
        `;

        document.body.appendChild(toast);

        // Use requestAnimationFrame for smooth animation
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        // Auto remove
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        }, duration);
    }

    // Progress bar animation - PERFORMANCE OPTIMIZED
    animateProgressBar(barElement, targetValue, duration = 1000) {
        const startValue = 0;
        const startTime = Date.now();

        const animate = () => {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);

            const currentValue = startValue + (targetValue - startValue) * this.easeOutQuart(progress);
            barElement.style.width = currentValue + '%';

            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };

        requestAnimationFrame(animate);
    }

    // Debounce utility for performance
    debounce(func, wait) {
        return (...args) => {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(() => func.apply(this, args), wait);
        };
    }

    // Throttle utility for performance
    throttle(func, limit) {
        return (...args) => {
            if (!this.throttleTimer) {
                func.apply(this, args);
                this.throttleTimer = setTimeout(() => {
                    this.throttleTimer = null;
                }, limit);
            }
        };
    }

    // Easing functions
    easeOutQuart(t) {
        return 1 - Math.pow(1 - t, 4);
    }

    easeInOutCubic(t) {
        return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }
}

// Initialize animation manager with performance optimizations
let animationManager;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        animationManager = new AnimationManager();
    });
} else {
    animationManager = new AnimationManager();
}

// Global utility functions - PERFORMANCE OPTIMIZED
window.showModal = (modalId) => {
    if (animationManager) {
        animationManager.showModal(modalId);
    }
};

window.hideModal = (modalId) => {
    if (animationManager) {
        animationManager.hideModal(modalId);
    }
};

window.showToast = (message, type, duration) => {
    if (animationManager) {
        animationManager.showToast(message, type, duration);
    }
};

// Add CSS animations - PERFORMANCE OPTIMIZED
const style = document.createElement('style');
style.textContent = `
    @keyframes modalSlideIn {
        from {
            opacity: 0;
            transform: scale(0.9) translate3d(0, -20px, 0);
        }
        to {
            opacity: 1;
            transform: scale(1) translate3d(0, 0, 0);
        }
    }

    @keyframes modalSlideOut {
        from {
            opacity: 1;
            transform: scale(1) translate3d(0, 0, 0);
        }
        to {
            opacity: 0;
            transform: scale(0.9) translate3d(0, -20px, 0);
        }
    }

    @keyframes toastSlideIn {
        from {
            transform: translate3d(100%, 0, 0);
            opacity: 0;
        }
        to {
            transform: translate3d(0, 0, 0);
            opacity: 1;
        }
    }

    .toast {
        position: fixed;
        top: 20px;
        right: 20px;
        background: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        transform: translate3d(100%, 0, 0);
        opacity: 0;
        transition: all 0.3s ease;
        z-index: 10000;
        max-width: 300px;
        will-change: transform, opacity;
    }

    .toast.show {
        transform: translate3d(0, 0, 0);
        opacity: 1;
    }

    .toast-content {
        display: flex;
        align-items: center;
        padding: 12px 16px;
        gap: 12px;
    }

    .toast-message {
        flex: 1;
        font-size: 14px;
    }

    .toast-close {
        background: none;
        border: none;
        font-size: 18px;
        cursor: pointer;
        color: #666;
        padding: 0;
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .toast-info {
        border-left: 4px solid #667eea;
    }

    .toast-success {
        border-left: 4px solid #10b981;
    }

    .toast-warning {
        border-left: 4px solid #f59e0b;
    }

    .toast-error {
        border-left: 4px solid #ef4444;
    }

    .particle {
        position: absolute;
        pointer-events: none;
        z-index: 1000;
    }

    /* Page load animations are now handled by CSS transitions */
    .page-loading {
        opacity: 0;
        transform: translateY(20px);
    }
    
    .page-loaded {
        opacity: 1;
        transform: translateY(0);
        transition: all 0.6s ease-out;
    }

    nav.scrolled {
        background: rgba(102, 126, 234, 0.95) !important;
        backdrop-filter: blur(10px);
    }

    /* PERFORMANCE OPTIMIZATIONS */
    .gpu-accelerated {
        transform: translate3d(0, 0, 0);
        backface-visibility: hidden;
        perspective: 1000px;
    }

    /* Reduce motion for users who prefer it */
    @media (prefers-reduced-motion: reduce) {
        *,
        *::before,
        *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }
    }
`;

document.head.appendChild(style);
