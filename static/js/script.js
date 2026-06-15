document.addEventListener('DOMContentLoaded', () => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let progress = document.querySelector('.scroll-progress');

    if (!progress) {
        progress = document.createElement('div');
        progress.className = 'scroll-progress';
        document.body.appendChild(progress);
    }

    const header = document.querySelector('.main-header');
    const hero = document.querySelector('.hero-section');
    const heroVisual = document.querySelector('.hero-image');
    const headerContainer = document.querySelector('.header-container');
    let menuBtn = document.querySelector('.mobile-menu-btn');
    const nav = document.querySelector('.main-nav');
    const sidebar = document.querySelector('.sidebar');

    if (!menuBtn && nav && headerContainer) {
        menuBtn = document.createElement('button');
        menuBtn.type = 'button';
        menuBtn.className = 'mobile-menu-btn';
        menuBtn.setAttribute('aria-label', 'Open navigation menu');
        menuBtn.setAttribute('aria-expanded', 'false');
        menuBtn.innerHTML = '<i data-lucide="menu"></i>';
        headerContainer.appendChild(menuBtn);
    }

    if (menuBtn && nav) {
        const closeTopNav = () => {
            nav.classList.remove('active');
            menuBtn.setAttribute('aria-expanded', 'false');
        };

        menuBtn.addEventListener('click', () => {
            nav.classList.toggle('active');
            menuBtn.setAttribute('aria-expanded', nav.classList.contains('active') ? 'true' : 'false');
        });

        nav.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', closeTopNav);
        });

        document.addEventListener('click', (event) => {
            if (!nav.classList.contains('active')) return;
            if (nav.contains(event.target) || menuBtn.contains(event.target)) return;
            closeTopNav();
        });
    }

    if (sidebar) {
        if (!sidebar.id) sidebar.id = 'sidebar';

        // Restore scroll position
        const savedScroll = localStorage.getItem('sidebar-scroll');
        if (savedScroll) {
            sidebar.scrollTop = parseInt(savedScroll, 10);
        }

        // Save scroll position on scroll
        sidebar.addEventListener('scroll', () => {
            localStorage.setItem('sidebar-scroll', sidebar.scrollTop);
        });

        const topBar = document.querySelector('.top-bar');
        const topBarLeft = document.querySelector('.top-bar-left') || topBar;
        let sidebarToggle = document.querySelector('.sidebar-toggle-btn');
        let sidebarOverlay = document.querySelector('.sidebar-overlay');

        if (!sidebarOverlay) {
            sidebarOverlay = document.createElement('div');
            sidebarOverlay.className = 'sidebar-overlay';
            document.body.appendChild(sidebarOverlay);
        }

        if (!sidebarToggle && topBarLeft) {
            sidebarToggle = document.createElement('button');
            sidebarToggle.type = 'button';
            sidebarToggle.className = 'sidebar-toggle-btn';
            sidebarToggle.setAttribute('aria-label', 'Open dashboard menu');
            sidebarToggle.setAttribute('aria-controls', sidebar.id);
            sidebarToggle.setAttribute('aria-expanded', 'false');
            sidebarToggle.innerHTML = '<i data-lucide="menu"></i>';
            topBarLeft.prepend(sidebarToggle);
        }

        const setSidebarOpen = (isOpen) => {
            sidebar.classList.toggle('active', isOpen);
            sidebarOverlay.classList.toggle('active', isOpen);
            document.body.classList.toggle('sidebar-open', isOpen);
            if (sidebarToggle) {
                sidebarToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
                sidebarToggle.setAttribute('aria-label', isOpen ? 'Close dashboard menu' : 'Open dashboard menu');
            }
        };

        const closeSidebarOnMobile = () => {
            if (window.matchMedia('(max-width: 992px)').matches) {
                setSidebarOpen(false);
            }
        };

        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', () => {
                setSidebarOpen(!sidebar.classList.contains('active'));
            });
        }

        sidebarOverlay.addEventListener('click', () => setSidebarOpen(false));
        sidebar.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', closeSidebarOnMobile);
        });

        const currentPath = window.location.pathname.replace(/\/$/, '') || '/';
        const sidebarLinks = Array.from(sidebar.querySelectorAll('.sidebar-item[href]'));
        const currentSidebarLink = sidebarLinks.find((link) => {
            const linkPath = new URL(link.getAttribute('href'), window.location.origin).pathname.replace(/\/$/, '') || '/';
            return linkPath === currentPath;
        });

        if (currentSidebarLink) {
            sidebarLinks.forEach((link) => link.classList.remove('active'));
            currentSidebarLink.classList.add('active');
        }

        window.addEventListener('resize', () => {
            if (!window.matchMedia('(max-width: 992px)').matches) {
                setSidebarOpen(false);
            }
        });
    }

    const currentPath = window.location.pathname.replace(/\/$/, '') || '/';
    document.querySelectorAll('.main-nav .nav-link[href]').forEach((link) => {
        const href = link.getAttribute('href');
        if (!href || href.startsWith('#')) return;
        const linkPath = new URL(href, window.location.origin).pathname.replace(/\/$/, '') || '/';
        if (linkPath === currentPath) {
            document.querySelectorAll('.main-nav .nav-link.active').forEach((activeLink) => activeLink.classList.remove('active'));
            link.classList.add('active');
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        if (nav) nav.classList.remove('active');
        if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false');
        if (sidebar) {
            sidebar.classList.remove('active');
            document.querySelector('.sidebar-overlay')?.classList.remove('active');
            document.body.classList.remove('sidebar-open');
            document.querySelector('.sidebar-toggle-btn')?.setAttribute('aria-expanded', 'false');
        }
    });

    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    document.querySelectorAll('a[href="/logout"]').forEach((link) => {
        link.addEventListener('click', (event) => {
            event.preventDefault();
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/logout';

            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (token) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = '_csrf_token';
                input.value = token;
                form.appendChild(input);
            }

            document.body.appendChild(form);
            form.submit();
        });
    });

    const updateScrollEffects = () => {
        if (header) {
            header.classList.toggle('is-scrolled', window.scrollY > 8);
        }

        const scrollable = document.documentElement.scrollHeight - window.innerHeight;
        const progressValue = scrollable > 0 ? window.scrollY / scrollable : 0;
        progress.style.transform = `scaleX(${Math.min(Math.max(progressValue, 0), 1)})`;

        if (hero && !reduceMotion) {
            hero.style.backgroundPosition = `center ${Math.round(window.scrollY * 0.18)}px`;
        }

        if (heroVisual && !reduceMotion) {
            heroVisual.style.setProperty('--hero-visual-shift', `${Math.round(window.scrollY * -0.035)}px`);
        }
    };

    let ticking = false;
    const requestScrollUpdate = () => {
        if (ticking) return;
        ticking = true;

        window.requestAnimationFrame(() => {
            updateScrollEffects();
            ticking = false;
        });
    };

    updateScrollEffects();
    window.addEventListener('scroll', requestScrollUpdate, { passive: true });

    const revealTargets = Array.from(document.querySelectorAll([
        '.section-header',
        '.hero-stat',
        '.facility-card',
        '.feature-list li',
        '.teacher-card',
        '.service-card',
        '.gallery-item',
        '.auth-container',
        '.welcome-card',
        '.dashboard-grid > *',
        '.content-wrapper > .auth-container',
        '.cta-section > .container',
        '.footer-col'
    ].join(',')));

    const textTargets = Array.from(document.querySelectorAll([
        '.hero-tag',
        '.hero-title',
        '.hero-description',
        '.section-subtitle',
        '.section-title',
        '.section-text',
        '.feature-list h3',
        '.feature-list p',
        '.facility-card h3',
        '.facility-card p',
        '.teacher-info h3',
        '.teacher-info span',
        '.service-content h3',
        '.service-content p',
        '.cta-section h2',
        '.cta-section p',
        '.branch-title',
        '.main-footer h3',
        '.footer-col p',
        '.contact-list li'
    ].join(',')));

    const splitAnimatedText = (el) => {
        if (el.dataset.textSplit || el.children.length || reduceMotion) return;

        const text = el.textContent.trim();
        if (!text || text.length > 90) return;

        el.dataset.textSplit = 'true';
        el.setAttribute('aria-label', text);
        el.textContent = '';
        el.classList.add('scroll-text-split');

        text.split(/(\s+)/).forEach((part, index) => {
            if (!part.trim()) {
                el.appendChild(document.createTextNode(part));
                return;
            }

            const word = document.createElement('span');
            word.className = 'scroll-word';
            word.setAttribute('aria-hidden', 'true');
            word.style.setProperty('--word-delay', `${Math.min(index, 10) * 32}ms`);
            word.textContent = part;
            el.appendChild(word);
        });
    };

    revealTargets.forEach((el, index) => {
        el.classList.add('reveal-on-scroll');
        el.style.setProperty('--reveal-delay', `${Math.min(index % 6, 5) * 55}ms`);

        if (!el.dataset.reveal) {
            if (el.classList.contains('hero-stat') || el.classList.contains('facility-card')) {
                el.dataset.reveal = 'zoom';
            } else if (index % 3 === 1) {
                el.dataset.reveal = 'left';
            } else if (index % 3 === 2) {
                el.dataset.reveal = 'right';
            }
        }
    });

    textTargets.forEach((el, index) => {
        el.classList.add('text-reveal-on-scroll');
        el.style.setProperty('--text-delay', `${Math.min(index % 8, 7) * 35}ms`);

        if (el.matches('.hero-title, .section-title, .branch-title, .service-content h3, .facility-card h3')) {
            splitAnimatedText(el);
        }
    });

    const observedTargets = [...new Set([...revealTargets, ...textTargets])];

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                } else {
                    entry.target.classList.remove('is-visible');
                }
            });
        }, { threshold: 0.12 });

        observedTargets.forEach((el) => observer.observe(el));
    } else {
        observedTargets.forEach((el) => el.classList.add('is-visible'));
    }

    // Automatically convert static Flask flash messages to premium toasts
    const staticAlerts = document.querySelectorAll('.flash-messages .alert, .alert-box, .alert-danger, .alert');
    staticAlerts.forEach((alertEl) => {
        // Skip inline conditioning elements like username display by checking if it's within flash wrapper or alert-danger flash
        const isFlashed = alertEl.closest('.flash-messages') || alertEl.classList.contains('alert-danger') || alertEl.classList.contains('alert-success');
        if (!isFlashed) return;

        const text = alertEl.querySelector('span')?.textContent || alertEl.textContent.trim();
        if (!text) return;

        let type = 'info';
        if (alertEl.classList.contains('alert-danger') || alertEl.classList.contains('alert-error')) {
            type = 'error';
        } else if (alertEl.classList.contains('alert-success')) {
            type = 'success';
        } else if (alertEl.classList.contains('alert-warning')) {
            type = 'warning';
        }

        // Hide original static markup so it doesn't double-render
        alertEl.style.display = 'none';
        const parentMessages = alertEl.closest('.flash-messages');
        if (parentMessages) {
            parentMessages.style.display = 'none';
        }

        // Show the elegant toast notification!
        window.showToast(text, type);
    });
});

// Global Aesthetic Toast Notification System
window.showToast = function(message, type = 'success', duration = 4000) {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const normalizedType = ['success', 'error', 'danger', 'warning', 'info'].includes(type) ? type : 'info';
    toast.className = `toast-notification toast-${normalizedType}`;
    
    let accentColor = '#1f6f78'; // fallback
    let iconName = 'check-circle';
    if (normalizedType === 'success') {
        accentColor = '#10b981';
        iconName = 'check-circle';
    } else if (normalizedType === 'error' || normalizedType === 'danger') {
        accentColor = '#ef4444';
        iconName = 'alert-circle';
    } else if (normalizedType === 'warning') {
        accentColor = '#f59e0b';
        iconName = 'alert-triangle';
    } else if (normalizedType === 'info') {
        accentColor = '#3b82f6';
        iconName = 'info';
    }

    toast.style.setProperty('--toast-accent', accentColor);

    const toastContent = document.createElement('div');
    toastContent.className = 'toast-content';

    const icon = document.createElement('div');
    icon.className = 'toast-icon';
    icon.innerHTML = `<i data-lucide="${iconName}" style="width: 16px; height: 16px;"></i>`;

    const messageText = document.createElement('span');
    messageText.textContent = String(message ?? '');

    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'toast-close-btn';
    closeButton.setAttribute('aria-label', 'Close notification');
    closeButton.innerHTML = '<i data-lucide="x" style="width: 16px; height: 16px;"></i>';

    const progress = document.createElement('div');
    progress.className = 'toast-progress';

    toastContent.append(icon, messageText);
    toast.append(toastContent, closeButton, progress);

    container.appendChild(toast);
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // Trigger reveal reflow
    toast.offsetHeight;
    toast.classList.add('show');

    // Animate shrinking progress bar
    const progressBar = toast.querySelector('.toast-progress');
    progressBar.style.animation = `shrinkProgress ${duration}ms linear forwards`;

    const closeToast = () => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
            if (container.children.length === 0) {
                container.remove();
            }
        }, 400);
    };

    closeButton.addEventListener('click', closeToast);

    let autoDismiss = setTimeout(closeToast, duration);
    let startTime = Date.now();
    let remainingTime = duration;

    // Pause countdown on hover
    toast.addEventListener('mouseenter', () => {
        clearTimeout(autoDismiss);
        progressBar.style.animationPlayState = 'paused';
        remainingTime -= Date.now() - startTime;
    });

    toast.addEventListener('mouseleave', () => {
        progressBar.style.animationPlayState = 'running';
        startTime = Date.now();
        autoDismiss = setTimeout(closeToast, remainingTime);
    });
};

window.showAlert = function(message, type = 'info', duration = 4500) {
    window.showToast(message, type, duration);
};

window.alert = function(message) {
    window.showAlert(message, 'info');
};

// Global Aesthetic Confirmation Modal System
window.showConfirm = function(message, onConfirm, title = "Confirm Action") {
    // Prevent duplicates
    if (document.querySelector('.confirm-overlay')) return;

    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';

    overlay.innerHTML = `
        <div class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
            <div class="confirm-icon-wrapper">
                <i data-lucide="alert-triangle" style="width: 28px; height: 28px;"></i>
            </div>
            <div class="confirm-title" id="confirm-title"></div>
            <div class="confirm-message" id="confirm-message"></div>
            <div class="confirm-buttons">
                <button type="button" class="confirm-btn confirm-btn-cancel">Cancel</button>
                <button type="button" class="confirm-btn confirm-btn-ok">OK</button>
            </div>
        </div>
    `;

    overlay.querySelector('.confirm-title').textContent = title;
    overlay.querySelector('.confirm-message').textContent = String(message ?? '');

    document.body.appendChild(overlay);
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // Trigger reveal reflow
    overlay.offsetHeight;
    overlay.classList.add('show');

    let isClosing = false;
    const closeConfirm = () => {
        if (isClosing) return;
        isClosing = true;
        document.removeEventListener('keydown', keyHandler);
        overlay.classList.remove('show');
        setTimeout(() => {
            overlay.remove();
        }, 300);
    };

    overlay.querySelector('.confirm-btn-cancel').addEventListener('click', closeConfirm);
    
    overlay.querySelector('.confirm-btn-ok').addEventListener('click', () => {
        closeConfirm();
        if (onConfirm) onConfirm();
    });

    // Close on clicking overlay background
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeConfirm();
        }
    });

    // Close on Escape, confirm on Enter key
    const keyHandler = (e) => {
        if (e.key === 'Escape') {
            closeConfirm();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            closeConfirm();
            if (onConfirm) onConfirm();
        }
    };
    document.addEventListener('keydown', keyHandler);
};

// Intercept native form onsubmit confirm dialogues and use our gorgeous custom modal
document.addEventListener('submit', function(event) {
    if (event.target.dataset.confirmed === 'true') {
        return;
    }
    
    const onSubmitAttr = event.target.getAttribute('onsubmit');
    if (onSubmitAttr && onSubmitAttr.includes('confirm(')) {
        event.preventDefault(); // Stop submission!
        event.stopImmediatePropagation();
        
        let message = "Are you sure you want to proceed?";
        const match = onSubmitAttr.match(/confirm\(['"](.*?)['"]\)/);
        if (match && match[1]) {
            message = match[1];
        }
        
        window.showConfirm(message, () => {
            event.target.dataset.confirmed = 'true';
            event.target.submit(); // Submit programmatically!
        });
    }
}, true); // Use capture phase to intercept before inline onsubmit fires!

// Intercept native onclick confirm dialogues on anchors, buttons, and inputs
document.addEventListener('click', function(event) {
    const target = event.target.closest('a, button, input[type="submit"]');
    if (!target) return;
    
    if (target.dataset.confirmed === 'true') {
        return;
    }
    
    const onClickAttr = target.getAttribute('onclick');
    if (onClickAttr && onClickAttr.includes('confirm(')) {
        event.preventDefault(); // Stop default action!
        event.stopImmediatePropagation();
        
        let message = "Are you sure you want to proceed?";
        const match = onClickAttr.match(/confirm\(['"](.*?)['"]\)/);
        if (match && match[1]) {
            message = match[1];
        }
        
        window.showConfirm(message, () => {
            target.dataset.confirmed = 'true';
            target.removeAttribute('onclick');

            const form = target.closest('form');
            const isSubmitControl = form && (target.matches('button:not([type]), button[type="submit"], input[type="submit"]'));
            if (isSubmitControl) {
                if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit(target);
                } else {
                    form.submit();
                }
                return;
            }

            if (target.matches('a[href]')) {
                const href = target.getAttribute('href');
                if (href && href !== '#') {
                    window.location.href = href;
                }
                return;
            }

            target.click();
        });
    }
}, true); // Use capture phase to intercept before inline onclick fires!

/* PREMIUM TESTIMONIAL REVIEWS & INTERACTIVE RATINGS SELECTOR */
document.addEventListener('DOMContentLoaded', () => {
    const writeBtn = document.getElementById('writeReviewBtn');
    const modal = document.getElementById('reviewModal');
    const closeBtn = document.getElementById('closeReviewModal');
    const stars = document.querySelectorAll('.star-rating-select i');
    const ratingInput = document.getElementById('ratingInput');

    if (writeBtn && modal) {
        writeBtn.addEventListener('click', () => {
            modal.classList.add('active');
            document.body.style.overflow = 'hidden'; // prevent scroll
        });

        const closeModal = () => {
            modal.classList.remove('active');
            document.body.style.overflow = ''; // restore scroll
        };

        if (closeBtn) {
            closeBtn.addEventListener('click', closeModal);
        }

        // Close on overlay click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('active')) {
                closeModal();
            }
        });

        // Interactive star selection
        stars.forEach(star => {
            star.addEventListener('click', () => {
                const value = parseInt(star.getAttribute('data-value'));
                ratingInput.value = value;
                
                // Highlight up to selected value
                stars.forEach(s => {
                    const sVal = parseInt(s.getAttribute('data-value'));
                    if (sVal <= value) {
                        s.className = 'fas fa-star';
                        s.style.color = 'var(--accent-color)';
                    } else {
                        s.className = 'far fa-star';
                        s.style.color = '#cbd5e1';
                    }
                });
            });

            // Hover preview effect
            star.addEventListener('mouseenter', () => {
                const value = parseInt(star.getAttribute('data-value'));
                stars.forEach(s => {
                    const sVal = parseInt(s.getAttribute('data-value'));
                    if (sVal <= value) {
                        s.className = 'fas fa-star';
                        s.style.color = 'var(--accent-color)';
                    } else {
                        s.className = 'far fa-star';
                        s.style.color = '#cbd5e1';
                    }
                });
            });
        });

        // Reset hover preview to currently selected rating when leaving stars container
        const starContainer = document.querySelector('.star-rating-select');
        if (starContainer) {
            starContainer.addEventListener('mouseleave', () => {
                const currentRating = parseInt(ratingInput.value || 5);
                stars.forEach(s => {
                    const sVal = parseInt(s.getAttribute('data-value'));
                    if (sVal <= currentRating) {
                        s.className = 'fas fa-star';
                        s.style.color = 'var(--accent-color)';
                    } else {
                        s.className = 'far fa-star';
                        s.style.color = '#cbd5e1';
                    }
                });
            });
        }
    }
});
