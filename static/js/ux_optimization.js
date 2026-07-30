/**
 * Enterprise Apple Fluid Glass UX & Theme Engine
 * Provides global fluid animated background canvas, liquid ripple engine,
 * cross-tab theme synchronization, and hardware-accelerated touch physics.
 */

(function () {
    'use strict';

    // 0. INSTANT ANTI-FOUC THEME APPLICATION (RUNS IMMEDIATELY ON INITIAL LOAD & REFRESH)
    (function applyInstantTheme() {
        try {
            const savedTheme = localStorage.getItem('theme');
            const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
            const targetTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
            document.documentElement.setAttribute('data-theme', targetTheme);
        } catch (e) {}
    })();

    // 0.1 MODE-AWARE SKELETON SCREEN GENERATOR
    function getSkeletonHTML() {
        return `
            <div class="skeleton-screen">
                <div class="skeleton-grid">
                    <div class="skeleton-card"><div class="skeleton-shimmer"></div></div>
                    <div class="skeleton-card"><div class="skeleton-shimmer"></div></div>
                    <div class="skeleton-card"><div class="skeleton-shimmer"></div></div>
                </div>
                <div class="skeleton-table-box"><div class="skeleton-shimmer"></div></div>
            </div>
        `;
    }

    // 1. GLOBAL AMBIENT FLUID BACKGROUND CANVAS INJECTION
    function initGlobalFluidCanvas() {
        if (document.getElementById('apple-fluid-bg')) return;

        const bgContainer = document.createElement('div');
        bgContainer.id = 'apple-fluid-bg';
        bgContainer.innerHTML = `
            <div class="fluid-blob fluid-blob-1"></div>
            <div class="fluid-blob fluid-blob-2"></div>
            <div class="fluid-blob fluid-blob-3"></div>
            <div class="fluid-blob fluid-blob-4"></div>
        `;
        document.body.prepend(bgContainer);

        // Dynamic Parallax Drift on Mouse/Touch Movement
        let mouseX = 0, mouseY = 0;
        let targetX = 0, targetY = 0;

        window.addEventListener('pointermove', function (e) {
            targetX = (e.clientX / window.innerWidth - 0.5) * 40;
            targetY = (e.clientY / window.innerHeight - 0.5) * 40;
        }, { passive: true });

        function animateBlobs() {
            mouseX += (targetX - mouseX) * 0.05;
            mouseY += (targetY - mouseY) * 0.05;
            bgContainer.style.transform = `translate3d(${mouseX}px, ${mouseY}px, 0)`;
            requestAnimationFrame(animateBlobs);
        }
        requestAnimationFrame(animateBlobs);
    }

    // 2. GLOBAL INTERACTIVE LIQUID RIPPLE CANVAS ENGINE
    function initGlobalLiquidRipple() {
        let canvas = document.getElementById('liquid-ripple-canvas');
        if (!canvas) {
            canvas = document.createElement('canvas');
            canvas.id = 'liquid-ripple-canvas';
            document.body.appendChild(canvas);
        }

        const ctx = canvas.getContext('2d');
        let ripples = [];

        function resizeCanvas() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }
        resizeCanvas();
        window.addEventListener('resize', resizeCanvas, { passive: true });

        window.addEventListener('pointerdown', function (e) {
            ripples.push({
                x: e.clientX,
                y: e.clientY,
                radius: 4,
                maxRadius: 36,
                opacity: 0.28,
                color: document.documentElement.getAttribute('data-theme') === 'dark' ? 'rgba(56, 189, 248, ' : 'rgba(31, 111, 120, '
            });
        }, { passive: true });

        function drawRipples() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            for (let i = ripples.length - 1; i >= 0; i--) {
                const r = ripples[i];
                r.radius += (r.maxRadius - r.radius) * 0.08 + 2;
                r.opacity *= 0.94;

                if (r.opacity < 0.01) {
                    ripples.splice(i, 1);
                    continue;
                }

                ctx.beginPath();
                ctx.arc(r.x, r.y, r.radius, 0, Math.PI * 2);
                ctx.strokeStyle = r.color + r.opacity + ')';
                ctx.lineWidth = 2.5;
                ctx.stroke();
            }
            requestAnimationFrame(drawRipples);
        }
        requestAnimationFrame(drawRipples);
    }

    // 3. GLOBAL THEME PROVIDER & CROSS-TAB SYNCHRONIZATION
    function initThemeEngine() {
        const savedTheme = localStorage.getItem('theme');
        const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        const currentTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');

        applyTheme(currentTheme);

        // Cross-tab synchronization
        window.addEventListener('storage', function (e) {
            if (e.key === 'theme' && e.newValue) {
                applyTheme(e.newValue);
            }
        });

        // Inject floating theme switcher pill if missing
        if (!document.querySelector('.theme-toggle-btn')) {
            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'theme-toggle-btn';
            toggleBtn.type = 'button';
            toggleBtn.setAttribute('aria-label', 'Toggle Theme');
            updateToggleContent(toggleBtn, currentTheme);

            toggleBtn.addEventListener('click', function () {
                const activeTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
                applyTheme(activeTheme);
                localStorage.setItem('theme', activeTheme);
            });

            document.body.appendChild(toggleBtn);
        }
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        const toggleBtn = document.querySelector('.theme-toggle-btn');
        if (toggleBtn) updateToggleContent(toggleBtn, theme);
    }

    function updateToggleContent(btn, theme) {
        btn.innerHTML = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
    }

    // 4. INTENT-BASED ROUTE PREFETCHER
    const prefetchedUrls = new Set();
    let hoverTimer = null;

    function prefetchUrl(url) {
        if (!url || prefetchedUrls.has(url)) return;
        if (url.includes('/logout') || url.includes('/delete') || url.includes('#') || url.startsWith('http') || url.startsWith('javascript:')) return;

        prefetchedUrls.add(url);
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = url;
        link.as = 'document';
        document.head.appendChild(link);
    }

    function handleLinkHover(e) {
        const link = e.target.closest('a');
        if (!link || !link.href) return;
        const url = link.getAttribute('href');
        if (!url) return;

        hoverTimer = setTimeout(() => {
            prefetchUrl(url);
        }, 65);
    }

    function clearLinkHover() {
        if (hoverTimer) {
            clearTimeout(hoverTimer);
            hoverTimer = null;
        }
    }

    // 5. INTERNAL AJAX FORM SUBMISSION & ZERO REFRESH ENGINE
    function initInternalFormHandler() {
        document.addEventListener('submit', async function (e) {
            const form = e.target;
            if (form.getAttribute('data-no-ajax') === 'true' || form.getAttribute('target') === '_blank') {
                return;
            }

            const mainContent = document.querySelector('.main-content');
            if (!mainContent) return;

            e.preventDefault();

            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            let originalText = '';
            if (submitBtn) {
                originalText = submitBtn.innerHTML || submitBtn.value;
                submitBtn.disabled = true;
                if (submitBtn.tagName === 'BUTTON') {
                    submitBtn.innerHTML = '<span class="btn-spinner"></span> Updating...';
                }
            }

            mainContent.style.transition = 'opacity 180ms ease, transform 180ms ease';
            mainContent.style.opacity = '0.4';
            mainContent.style.transform = 'translateY(4px)';

            try {
                const actionUrl = form.getAttribute('action') || window.location.href;
                const method = (form.getAttribute('method') || 'POST').toUpperCase();
                const formData = new FormData(form);

                const options = {
                    method: method,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                };

                if (method === 'GET') {
                    const params = new URLSearchParams(formData).toString();
                    const targetUrl = actionUrl.includes('?') ? `${actionUrl}&${params}` : `${actionUrl}?${params}`;
                    const res = await fetch(targetUrl, options);
                    const htmlText = await res.text();
                    updateMainContent(htmlText, res.url);
                } else {
                    options.body = formData;
                    const res = await fetch(actionUrl, options);
                    const htmlText = await res.text();
                    updateMainContent(htmlText, res.url);
                }

            } catch (err) {
                console.error('Internal form submission error:', err);
                form.submit();
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    if (submitBtn.tagName === 'BUTTON') submitBtn.innerHTML = originalText;
                }
                mainContent.style.opacity = '1';
                mainContent.style.transform = 'none';
            }
        });

        function updateMainContent(htmlText, finalUrl) {
            const mainContent = document.querySelector('.main-content');
            if (!mainContent) return;

            const parser = new DOMParser();
            const newDoc = parser.parseFromString(htmlText, 'text/html');
            const newMain = newDoc.querySelector('.main-content');

            if (newMain) {
                mainContent.innerHTML = newMain.innerHTML;
                document.title = newDoc.title || document.title;

                if (finalUrl && finalUrl !== window.location.href) {
                    history.pushState({ path: finalUrl }, '', finalUrl);
                }

                if (window.lucide && typeof window.lucide.createIcons === 'function') {
                    window.lucide.createIcons();
                }

                newMain.querySelectorAll('script').forEach(script => {
                    const newScript = document.createElement('script');
                    Array.from(script.attributes).forEach(attr => newScript.setAttribute(attr.name, attr.value));
                    newScript.appendChild(document.createTextNode(script.innerHTML));
                    document.body.appendChild(newScript).parentNode.removeChild(newScript);
                });
            }
        }
    }

    // SVG TURBULENCE LIQUID DISPLACEMENT FILTER (#lg-dist)
    function initSVGDisplacementFilter() {
        if (document.getElementById('lg-dist-svg')) return;
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.id = 'lg-dist-svg';
        svg.setAttribute('style', 'position: absolute; width: 0; height: 0; pointer-events: none; overflow: hidden;');
        svg.innerHTML = `
            <filter id="lg-dist" x="0%" y="0%" width="100%" height="100%">
                <feTurbulence type="fractalNoise" baseFrequency="0.008 0.008" numOctaves="2" seed="92" result="noise" />
                <feGaussianBlur in="noise" stdDeviation="2" result="blurred" />
                <feDisplacementMap in="SourceGraphic" in2="blurred" scale="70" xChannelSelector="R" yChannelSelector="G" />
            </filter>
        `;
        document.body.appendChild(svg);
    }

    // 6. SEAMLESS SINGLE PAGE APPLICATION (SPA) NAVIGATION ENGINE
    function initSPANavigation() {
        let isNavigating = false;

        async function loadPageContent(url, pushHistory = true) {
            const mainContent = document.querySelector('.main-content');
            const sidebar = document.querySelector('.sidebar');
            if (!mainContent || isNavigating) return false;

            isNavigating = true;
            mainContent.style.transition = 'opacity 180ms ease, transform 180ms ease';
            mainContent.style.opacity = '0.4';
            mainContent.style.transform = 'translateY(4px)';

            try {
                const response = await fetch(url, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });

                if (!response.ok) {
                    window.location.href = url;
                    return;
                }

                const htmlText = await response.text();
                const parser = new DOMParser();
                const newDoc = parser.parseFromString(htmlText, 'text/html');

                const newMain = newDoc.querySelector('.main-content');
                if (!newMain) {
                    window.location.href = url;
                    return;
                }

                // Swap right-side main content directly with 0ms delay
                mainContent.innerHTML = newMain.innerHTML;
                document.title = newDoc.title || document.title;

                if (pushHistory) {
                    history.pushState({ path: url }, '', url);
                }

                // Update active sidebar pill highlight smoothly
                if (sidebar) {
                    const currentPath = new URL(url, window.location.origin).pathname.replace(/\/$/, '') || '/';
                    sidebar.querySelectorAll('.sidebar-item').forEach(item => {
                        const href = item.getAttribute('href');
                        if (href) {
                            const itemPath = new URL(href, window.location.origin).pathname.replace(/\/$/, '') || '/';
                            if (itemPath === currentPath) {
                                item.classList.add('active');
                            } else {
                                item.classList.remove('active');
                            }
                        }
                    });
                }

                // Re-initialize Lucide Icons if available
                if (window.lucide && typeof window.lucide.createIcons === 'function') {
                    window.lucide.createIcons();
                }

                // Execute scripts inside swapped HTML if any
                newMain.querySelectorAll('script').forEach(script => {
                    const newScript = document.createElement('script');
                    Array.from(script.attributes).forEach(attr => newScript.setAttribute(attr.name, attr.value));
                    newScript.appendChild(document.createTextNode(script.innerHTML));
                    document.body.appendChild(newScript).parentNode.removeChild(newScript);
                });

                // Smooth fade back in
                mainContent.style.opacity = '1';
                mainContent.style.transform = 'none';

                // Scroll right side content top smoothly
                window.scrollTo({ top: 0, behavior: 'smooth' });

            } catch (err) {
                console.error('SPA Navigation error:', err);
                window.location.href = url;
            } finally {
                clearTimeout(skeletonTimer);
                isNavigating = false;
            }
        }

        // Intercept ALL dashboard & admin link clicks for Zero Full-Page Refreshes
        document.addEventListener('click', function (e) {
            const link = e.target.closest('a[href]');
            if (!link) return;

            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.includes('/logout') || link.getAttribute('target') === '_blank' || href.startsWith('http') || href.startsWith('mailto:')) {
                return;
            }

            const mainContent = document.querySelector('.main-content');
            if (!mainContent) return;

            e.preventDefault();
            loadPageContent(href, true);
        });

        // Handle Browser Back & Forward buttons
        window.addEventListener('popstate', function (e) {
            if (e.state && e.state.path) {
                loadPageContent(e.state.path, false);
            } else if (window.location.pathname) {
                loadPageContent(window.location.pathname, false);
            }
        });
    }

    // 7. INITIALIZE ON DOM READY
    function init() {
        initGlobalFluidCanvas();
        initGlobalLiquidRipple();
        initSVGDisplacementFilter();
        initThemeEngine();
        initOptimisticForms();
        initSPANavigation();

        document.addEventListener('pointerenter', handleLinkHover, true);
        document.addEventListener('pointerleave', clearLinkHover, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
