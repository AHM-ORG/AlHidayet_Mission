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

    const hamburgerMarkup = '<span class="hamburger-box"><span class="hamburger-line"></span><span class="hamburger-line"></span><span class="hamburger-line"></span></span>';

    if (nav) {
        if (!nav.id) nav.id = 'mainNav';
        if (!nav.getAttribute('aria-label')) nav.setAttribute('aria-label', 'Primary Navigation');
    }

    if (!menuBtn && nav && headerContainer) {
        menuBtn = document.createElement('button');
        menuBtn.type = 'button';
        menuBtn.className = 'mobile-menu-btn';
        menuBtn.setAttribute('aria-label', 'Open navigation menu');
        menuBtn.setAttribute('aria-expanded', 'false');
        menuBtn.setAttribute('aria-controls', nav.id);
        menuBtn.innerHTML = hamburgerMarkup;
        headerContainer.appendChild(menuBtn);
    } else if (menuBtn) {
        if (!menuBtn.querySelector('.hamburger-box')) {
            menuBtn.innerHTML = hamburgerMarkup;
        }
        if (nav) {
            menuBtn.setAttribute('aria-controls', nav.id);
            if (!menuBtn.getAttribute('aria-label')) menuBtn.setAttribute('aria-label', 'Open navigation menu');
            if (!menuBtn.getAttribute('aria-expanded')) menuBtn.setAttribute('aria-expanded', 'false');
        }
    }

    if (menuBtn && nav) {
        let navOverlay = document.querySelector('.main-nav-overlay');
        if (!navOverlay) {
            navOverlay = document.createElement('div');
            navOverlay.className = 'main-nav-overlay';
            navOverlay.setAttribute('aria-hidden', 'true');
            document.body.appendChild(navOverlay);
        }

        let isNavTransitioning = false;
        let lastNavToggleTime = 0;
        let lastFocusedElement = null;

        const openTopNav = () => {
            lastFocusedElement = document.activeElement;
            lastNavToggleTime = Date.now();
            isNavTransitioning = true;
            nav.classList.add('active');
            menuBtn.classList.add('active');
            menuBtn.setAttribute('aria-expanded', 'true');
            menuBtn.setAttribute('aria-label', 'Close navigation menu');
            navOverlay.classList.add('active');
            navOverlay.removeAttribute('aria-hidden');
            document.body.classList.add('mobile-nav-open');
            setTimeout(() => {
                isNavTransitioning = false;
                const closeBtn = nav.querySelector('.nav-drawer-close');
                const firstLink = nav.querySelector('.nav-link, a');
                if (closeBtn) {
                    closeBtn.focus();
                } else if (firstLink) {
                    firstLink.focus();
                }
            }, 60);
        };

        const closeTopNav = () => {
            if (Date.now() - lastNavToggleTime < 200) return;
            isNavTransitioning = true;
            nav.classList.remove('active');
            menuBtn.classList.remove('active');
            menuBtn.setAttribute('aria-expanded', 'false');
            menuBtn.setAttribute('aria-label', 'Open navigation menu');
            navOverlay.classList.remove('active');
            navOverlay.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('mobile-nav-open');
            setTimeout(() => {
                isNavTransitioning = false;
                if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
                    lastFocusedElement.focus();
                } else if (menuBtn) {
                    menuBtn.focus();
                }
            }, 60);
        };

        const toggleTopNav = (e) => {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            if (Date.now() - lastNavToggleTime < 200) return;
            if (nav.classList.contains('active')) {
                closeTopNav();
            } else {
                openTopNav();
            }
        };

        // Trap focus inside open mobile drawer for keyboard accessibility
        nav.addEventListener('keydown', (e) => {
            if (e.key === 'Tab' && nav.classList.contains('active')) {
                const focusables = Array.from(nav.querySelectorAll('button, a, input, select, textarea, [tabindex]:not([tabindex="-1"])'))
                    .filter(el => !el.hasAttribute('disabled') && el.offsetParent !== null);
                if (focusables.length === 0) return;
                const first = focusables[0];
                const last = focusables[focusables.length - 1];
                if (e.shiftKey) {
                    if (document.activeElement === first) {
                        e.preventDefault();
                        last.focus();
                    }
                } else {
                    if (document.activeElement === last) {
                        e.preventDefault();
                        first.focus();
                    }
                }
            }
        });

        // Setup Sleek Minimalist Luxury Side Drawer Elements
        const setupSideDrawer = () => {
            // 1. Ensure Drawer Top Header exists with refined luxury styling
            if (!nav.querySelector('.nav-drawer-header')) {
                const headerLogo = document.querySelector('.main-header .logo img, .main-header .logo-img');
                const logoSrc = (headerLogo && headerLogo.getAttribute('src')) ? headerLogo.getAttribute('src') : '/static/images/logo.png';
                
                const drawerHeader = document.createElement('div');
                drawerHeader.className = 'nav-drawer-header';
                drawerHeader.innerHTML = `
                    <a href="/" class="nav-drawer-brand">
                        <img src="${logoSrc}" alt="AHM Crest" class="nav-drawer-logo">
                        <div class="nav-drawer-brand-text">
                            <span class="nav-drawer-school">Al-Hidayet <span class="highlight">Mission</span></span>
                            <span class="nav-drawer-tagline">Academic Excellence</span>
                        </div>
                    </a>
                    <button class="nav-drawer-close" aria-label="Close navigation menu" type="button">
                        <i data-lucide="x"></i>
                    </button>
                `;
                nav.insertBefore(drawerHeader, nav.firstChild);

                const drawerCloseBtn = drawerHeader.querySelector('.nav-drawer-close');
                if (drawerCloseBtn) {
                    drawerCloseBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        closeTopNav();
                    });
                }
            }

            // Detect if logged in from existing logout links
            const isLoggedIn = Boolean(nav.querySelector('a[href*="logout"]') || document.querySelector('.header-cta a[href*="logout"]'));

            // Remove legacy top quick actions and duplicate mobile-only nav links
            nav.querySelectorAll('.nav-drawer-quick-actions').forEach(el => el.remove());
            nav.querySelectorAll('.nav-link-mobile-only').forEach(el => el.remove());
            nav.querySelectorAll('.mobile-nav-cta').forEach(el => el.remove());

            // 2. Ensure Drawer Body exists for the smooth single-column list
            let drawerBody = nav.querySelector('.nav-drawer-body');
            if (!drawerBody) {
                drawerBody = document.createElement('div');
                drawerBody.className = 'nav-drawer-body';

                // Move all actual navigation links into drawerBody
                const allNavLinks = Array.from(nav.querySelectorAll(':scope > .nav-link'));
                allNavLinks.forEach(link => {
                    const href = (link.getAttribute('href') || '').toLowerCase();
                    if (href === '/dashboard' || href.includes('logout') || href.includes('login')) {
                        link.remove();
                    } else {
                        drawerBody.appendChild(link);
                    }
                });

                nav.appendChild(drawerBody);
            } else {
                // If drawerBody already existed, clean up any legacy grids, section titles, or quick actions
                drawerBody.querySelectorAll('.nav-drawer-quick-actions, .nav-drawer-section-title').forEach(el => el.remove());
                const grid = drawerBody.querySelector('.nav-drawer-grid');
                if (grid) {
                    Array.from(grid.querySelectorAll('.nav-link')).forEach(link => drawerBody.appendChild(link));
                    grid.remove();
                }
            }

            // 3. Map intuitive icons to each navigation item (Clean Inline Lucide Icon, NO square boxes)
            const getIconForLink = (text, href) => {
                const t = (text || '').toLowerCase().trim();
                const h = (href || '').toLowerCase().trim();
                if (t.includes('home') || h === '/' || h === '#home') return 'home';
                if (t.includes('about')) return 'sparkles';
                if (t.includes('service')) return 'layers';
                if (t.includes('gallery')) return 'image';
                if (t.includes('notice')) return 'bell';
                if (t.includes('fee')) return 'receipt';
                if (t.includes('review')) return 'star';
                if (t.includes('faq')) return 'help-circle';
                if (t.includes('contact')) return 'phone';
                if (t.includes('routine')) return 'calendar';
                if (t.includes('academic')) return 'book-open';
                if (t.includes('admission') || t.includes('apply')) return 'file-text';
                return 'compass';
            };

            // Format every link with sleek minimalist markup (no clunky square boxes)
            drawerBody.querySelectorAll('.nav-link').forEach(link => {
                const labelEl = link.querySelector('.nav-link-label');
                const rawText = (labelEl ? labelEl.textContent : link.textContent).trim();
                const href = link.getAttribute('href') || '';
                
                // Exclude any duplicate dashboard/logout that might still be present
                if (href === '/dashboard' || href.includes('logout') || href.includes('login')) {
                    link.remove();
                    return;
                }

                const iconName = getIconForLink(rawText, href);
                link.innerHTML = `
                    <span class="nav-link-left">
                        <i data-lucide="${iconName}" class="nav-link-icon"></i>
                        <span class="nav-link-label">${rawText}</span>
                    </span>
                    <i data-lucide="chevron-right" class="nav-link-arrow"></i>
                `;
            });

            // 4. Build or update the Sleek Account Card directly inside drawerBody (after Contact)
            let accountSection = nav.querySelector('.nav-drawer-account-section');
            if (!accountSection) {
                accountSection = document.createElement('div');
                accountSection.className = 'nav-drawer-account-section';
                accountSection.innerHTML = `
                    <div class="drawer-account-card">
                        <div class="account-card-header">
                            <div class="account-avatar">
                                <i data-lucide="${isLoggedIn ? 'user-check' : 'shield-check'}"></i>
                            </div>
                            <div class="account-meta">
                                <span class="account-badge">
                                    <span class="badge-dot"></span>
                                    ${isLoggedIn ? 'Active Session' : 'Official Portal'}
                                </span>
                                <span class="account-title">${isLoggedIn ? 'Signed In Account' : 'Student &amp; Parent Access'}</span>
                            </div>
                        </div>
                        <div class="account-card-actions">
                            <a href="/dashboard" class="account-btn account-btn-primary">
                                <i data-lucide="layout-dashboard"></i>
                                <span>Dashboard</span>
                            </a>
                            ${isLoggedIn ? `
                            <a href="/logout" class="account-btn account-btn-outline">
                                <i data-lucide="log-out"></i>
                                <span>Logout</span>
                            </a>` : `
                            <a href="/login/student" class="account-btn account-btn-outline">
                                <i data-lucide="log-in"></i>
                                <span>Portal Login</span>
                            </a>`}
                        </div>
                    </div>
                `;
            }
            // Always append accountSection at the end of drawerBody so it sits right after Contact
            drawerBody.appendChild(accountSection);

            // Clean up any separate nav-drawer-footer if present
            nav.querySelectorAll('.nav-drawer-footer').forEach(el => el.remove());

            // 5. Attach link click handlers to smoothly close drawer
            nav.querySelectorAll('a').forEach((link) => {
                link.addEventListener('click', closeTopNav);
            });

            // 6. Refresh Lucide icons
            if (window.lucide && typeof window.lucide.createIcons === 'function') {
                window.lucide.createIcons();
            }
        };

        setupSideDrawer();

        // Handle both standard click and touchend for zero-delay iPad execution
        menuBtn.addEventListener('click', toggleTopNav);
        menuBtn.addEventListener('touchend', (e) => {
            e.preventDefault();
            toggleTopNav(e);
        }, { passive: false });

        menuBtn.addEventListener('pointerdown', () => menuBtn.classList.add('is-pressed'));
        menuBtn.addEventListener('pointerup', () => menuBtn.classList.remove('is-pressed'));
        menuBtn.addEventListener('pointercancel', () => menuBtn.classList.remove('is-pressed'));

        navOverlay.addEventListener('click', (e) => {
            e.preventDefault();
            closeTopNav();
        });
        navOverlay.addEventListener('touchend', (e) => {
            e.preventDefault();
            closeTopNav();
        }, { passive: false });
        navOverlay.addEventListener('touchmove', (e) => {
            e.preventDefault();
        }, { passive: false });

        document.addEventListener('click', (event) => {
            if (isNavTransitioning || Date.now() - lastNavToggleTime < 350) return;
            if (!nav.classList.contains('active')) return;
            if (nav.contains(event.target) || menuBtn.contains(event.target) || event.target.closest('.mobile-menu-btn') || event.target.closest('.main-nav')) return;
            closeTopNav();
        });

        window.addEventListener('resize', () => {
            if (window.innerWidth > 1200 && nav.classList.contains('active')) {
                closeTopNav();
            }
        });
    }

    if (sidebar) {
        if (!sidebar.id) sidebar.id = 'sidebar';

        // Restore scroll position only on desktop
        if (!window.matchMedia('(max-width: 992px)').matches) {
            const savedScroll = localStorage.getItem('sidebar-scroll');
            if (savedScroll) {
                sidebar.scrollTop = parseInt(savedScroll, 10);
            }
        } else {
            localStorage.removeItem('sidebar-scroll');
            sidebar.scrollTop = 0;
            if (typeof sidebar.scrollTo === 'function') {
                sidebar.scrollTo({ top: 0, behavior: 'instant' });
            }
        }

        // Save scroll position on scroll only on desktop
        sidebar.addEventListener('scroll', () => {
            if (!window.matchMedia('(max-width: 992px)').matches) {
                localStorage.setItem('sidebar-scroll', sidebar.scrollTop);
            }
        });

        // Ensure sidebar header has a mobile close button
        let sidebarCloseBtn = sidebar.querySelector('.sidebar-close-btn');
        if (!sidebarCloseBtn) {
            const header = sidebar.querySelector('.sidebar-header');
            if (header) {
                sidebarCloseBtn = document.createElement('button');
                sidebarCloseBtn.type = 'button';
                sidebarCloseBtn.className = 'sidebar-close-btn';
                sidebarCloseBtn.setAttribute('aria-label', 'Close dashboard menu');
                sidebarCloseBtn.innerHTML = '<i data-lucide="x"></i>';
                header.appendChild(sidebarCloseBtn);
            }
        }
        if (sidebarCloseBtn) {
            sidebarCloseBtn.addEventListener('click', (e) => {
                e.preventDefault();
                setSidebarOpen(false);
            });
            sidebarCloseBtn.addEventListener('touchend', (e) => {
                e.preventDefault();
                setSidebarOpen(false);
            }, { passive: false });
        }

        const topBar = document.querySelector('.top-bar');
        let topBarLeft = document.querySelector('.top-bar-left');
        let sidebarToggle = document.querySelector('.sidebar-toggle-btn');
        let sidebarOverlay = document.querySelector('.sidebar-overlay');

        if (!sidebarOverlay) {
            sidebarOverlay = document.createElement('div');
            sidebarOverlay.className = 'sidebar-overlay';
            document.body.appendChild(sidebarOverlay);
        }

        if (topBar && !topBarLeft) {
            topBarLeft = document.createElement('div');
            topBarLeft.className = 'top-bar-left';
            const title = topBar.querySelector('.top-bar-title');
            if (title) {
                topBar.insertBefore(topBarLeft, title);
                topBarLeft.appendChild(title);
            } else {
                topBar.prepend(topBarLeft);
            }
        }

        if (!sidebarToggle && (topBarLeft || topBar)) {
            const container = topBarLeft || topBar;
            sidebarToggle = document.createElement('button');
            sidebarToggle.type = 'button';
            sidebarToggle.className = 'mobile-menu-btn sidebar-toggle-btn';
            sidebarToggle.setAttribute('aria-label', 'Open dashboard menu');
            sidebarToggle.setAttribute('aria-controls', sidebar.id);
            sidebarToggle.setAttribute('aria-expanded', 'false');
            sidebarToggle.innerHTML = `
                <span class="hamburger-box">
                    <span class="hamburger-line"></span>
                    <span class="hamburger-line"></span>
                    <span class="hamburger-line"></span>
                </span>
            `;
            container.prepend(sidebarToggle);
        } else if (sidebarToggle) {
            sidebarToggle.setAttribute('type', 'button');
            sidebarToggle.setAttribute('aria-controls', sidebar.id);
            if (!sidebarToggle.getAttribute('aria-expanded')) sidebarToggle.setAttribute('aria-expanded', 'false');
            if (!sidebarToggle.getAttribute('aria-label') || sidebarToggle.getAttribute('aria-label') === 'Toggle Navigation') {
                sidebarToggle.setAttribute('aria-label', 'Open dashboard menu');
            }
            if (!sidebarToggle.querySelector('.hamburger-box')) {
                sidebarToggle.innerHTML = `
                    <span class="hamburger-box">
                        <span class="hamburger-line"></span>
                        <span class="hamburger-line"></span>
                        <span class="hamburger-line"></span>
                    </span>
                `;
            }
        }

        // Harmonize Top Bar across all subpages with Homepage/Dashboard styling
        if (topBar && topBarLeft) {
            let topBarBrand = topBar.querySelector('.top-bar-brand');
            if (!topBarBrand) {
                const titleEl = topBar.querySelector('.top-bar-title');
                const rawTitle = titleEl ? titleEl.textContent.trim() : (document.title.split('-')[0].trim() || 'Portal');
                
                topBarBrand = document.createElement('a');
                topBarBrand.href = '/';
                topBarBrand.className = 'top-bar-brand';
                topBarBrand.setAttribute('aria-label', 'Al-Hidayet Mission Home');
                topBarBrand.innerHTML = `
                    <img src="/static/images/logo.png" alt="Al-Hidayet Mission Crest" class="top-bar-logo">
                    <div class="top-bar-brand-text">
                        <span class="top-bar-school">Al-Hidayet <span class="highlight">Mission</span></span>
                        <span class="top-bar-sub">${rawTitle}</span>
                    </div>
                `;

                if (titleEl) {
                    titleEl.replaceWith(topBarBrand);
                } else {
                    topBarLeft.appendChild(topBarBrand);
                }
            }

            // Harmonize Top Bar Right actions across all subpages
            let topBarRight = topBar.querySelector('.top-bar-right');
            if (!topBarRight) {
                topBarRight = document.createElement('div');
                topBarRight.className = 'top-bar-right';
                topBar.appendChild(topBarRight);
            }

            const currentPath = window.location.pathname.toLowerCase();
            if (!topBarRight.querySelector('a[href="/dashboard"]') && currentPath !== '/dashboard') {
                const dashBtn = document.createElement('a');
                dashBtn.href = '/dashboard';
                dashBtn.className = 'top-bar-action-btn';
                dashBtn.title = 'Dashboard';
                dashBtn.setAttribute('aria-label', 'Dashboard');
                dashBtn.innerHTML = '<i data-lucide="layout-dashboard"></i>';
                topBarRight.prepend(dashBtn);
            }

            if (!topBarRight.querySelector('a[href*="logout"]')) {
                const logoutBtn = document.createElement('a');
                logoutBtn.href = '/logout';
                logoutBtn.className = 'top-bar-logout-btn';
                logoutBtn.title = 'Logout';
                logoutBtn.setAttribute('aria-label', 'Logout');
                logoutBtn.innerHTML = '<i data-lucide="log-out"></i>';
                topBarRight.appendChild(logoutBtn);
            }
        }

        // Setup universal mobile table responsiveness & touch swipe cue
        const initUniversalMobileTables = () => {
            // Automatically wrap any stray table across all pages (excluding printable paper marksheets)
            document.querySelectorAll('table').forEach(tbl => {
                if (tbl.closest('.printable-marksheet, #printable-area, .info-tbl, .annual-tbl')) return;
                if (!tbl.closest('.table-scroll-container, .dash-table-container, .table-container, .table-responsive, .dash-table-responsive, .academics-table-scroll')) {
                    const wrap = document.createElement('div');
                    wrap.className = 'table-scroll-container';
                    tbl.parentNode.insertBefore(wrap, tbl);
                    wrap.appendChild(tbl);
                    tbl.classList.add('dash-table');
                }
            });

            const tableWrappers = document.querySelectorAll('.dash-table-container, .table-scroll-container, .table-container, .table-responsive, .dash-table-responsive, .academics-table-scroll');
            tableWrappers.forEach(container => {
                const table = container.querySelector('table');
                if (!table) return;

                const evaluateScrollability = () => {
                    if (window.innerWidth <= 992 && table.scrollWidth > container.clientWidth + 10) {
                        let hint = container.previousElementSibling;
                        if (!hint || !hint.classList.contains('mobile-table-hint')) {
                            hint = document.createElement('div');
                            hint.className = 'mobile-table-hint';
                            hint.innerHTML = '<i data-lucide="chevrons-left-right" style="width:13px;height:13px;"></i> <span>Swipe horizontally to view all columns &rarr;</span>';
                            container.parentNode.insertBefore(hint, container);
                            if (window.lucide && typeof window.lucide.createIcons === 'function') {
                                window.lucide.createIcons();
                            }
                        }
                    } else {
                        const hint = container.previousElementSibling;
                        if (hint && hint.classList.contains('mobile-table-hint')) {
                            hint.remove();
                        }
                    }
                };

                evaluateScrollability();
                window.addEventListener('resize', evaluateScrollability);
            });
        };
        initUniversalMobileTables();
        window.initUniversalMobileTables = initUniversalMobileTables;

        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            window.lucide.createIcons();
        }

        const setSidebarOpen = (isOpen) => {
            sidebar.classList.toggle('active', isOpen);
            sidebarOverlay.classList.toggle('active', isOpen);
            document.body.classList.toggle('sidebar-open', isOpen);
            if (isOpen && window.matchMedia('(max-width: 992px)').matches) {
                // Ensure full menu from Dashboard down is displayed from top
                sidebar.scrollTop = 0;
                if (typeof sidebar.scrollTo === 'function') {
                    sidebar.scrollTo({ top: 0, behavior: 'instant' });
                }
                requestAnimationFrame(() => {
                    sidebar.scrollTop = 0;
                });
                [30, 80, 180, 320].forEach(delay => {
                    setTimeout(() => {
                        sidebar.scrollTop = 0;
                        if (typeof sidebar.scrollTo === 'function') {
                            sidebar.scrollTo({ top: 0, behavior: 'instant' });
                        }
                    }, delay);
                });
            }
            document.querySelectorAll('.sidebar-toggle-btn, #sidebarToggle').forEach(btn => {
                btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
                btn.setAttribute('aria-label', isOpen ? 'Close dashboard menu' : 'Open dashboard menu');
            });
        };

        const closeSidebarOnMobile = () => {
            if (window.matchMedia('(max-width: 992px)').matches) {
                setSidebarOpen(false);
            }
        };

        let lastSidebarToggleTime = 0;
        const toggleSidebar = (e) => {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            if (Date.now() - lastSidebarToggleTime < 250) return;
            lastSidebarToggleTime = Date.now();
            setSidebarOpen(!sidebar.classList.contains('active'));
        };

        document.querySelectorAll('.sidebar-toggle-btn, #sidebarToggle').forEach(btn => {
            btn.addEventListener('click', toggleSidebar);
            btn.addEventListener('touchend', (e) => {
                e.preventDefault();
                toggleSidebar(e);
            }, { passive: false });
        });

        sidebarOverlay.addEventListener('click', (e) => {
            e.preventDefault();
            setSidebarOpen(false);
        });
        sidebarOverlay.addEventListener('touchend', (e) => {
            e.preventDefault();
            setSidebarOpen(false);
        }, { passive: false });
        sidebarOverlay.addEventListener('touchmove', (e) => {
            e.preventDefault();
        }, { passive: false });
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

    // Set Accessible Landmark Labels on Sidebar & TopBar
    document.querySelectorAll('.sidebar-nav').forEach((sbNav) => {
        if (!sbNav.getAttribute('aria-label')) {
            sbNav.setAttribute('aria-label', 'Sidebar Navigation');
        }
    });

    document.querySelectorAll('.top-bar').forEach((tb) => {
        if (!tb.getAttribute('role')) {
            tb.setAttribute('role', 'banner');
        }
    });

    const currentPath = window.location.pathname.replace(/\/$/, '') || '/';
    document.querySelectorAll('.main-nav .nav-link[href], .sidebar-nav .sidebar-item[href], .navbar .nav-links a[href]').forEach((link) => {
        const href = link.getAttribute('href');
        if (!href || href.startsWith('#')) return;
        const linkPath = new URL(href, window.location.origin).pathname.replace(/\/$/, '') || '/';
        if (linkPath === currentPath) {
            link.classList.add('active');
            link.setAttribute('aria-current', 'page');
        }
    });

    // Ensure all currently active links have aria-current="page"
    document.querySelectorAll('.main-nav .nav-link.active, .sidebar-nav .sidebar-item.active, .navbar a.active').forEach((activeEl) => {
        activeEl.setAttribute('aria-current', 'page');
    });

    // Universal Escape Key Handler
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape' && event.key !== 'Esc') return;
        if (typeof closeTopNav === 'function' && nav && nav.classList.contains('active')) {
            closeTopNav();
        } else if (nav && nav.classList.contains('active')) {
            nav.classList.remove('active');
            document.querySelector('.main-nav-overlay')?.classList.remove('active');
            document.body.classList.remove('mobile-nav-open');
            if (menuBtn) {
                menuBtn.classList.remove('active');
                menuBtn.setAttribute('aria-expanded', 'false');
                menuBtn.focus();
            }
        }
        if (sidebar && sidebar.classList.contains('active')) {
            if (typeof setSidebarOpen === 'function') {
                setSidebarOpen(false);
            } else {
                sidebar.classList.remove('active');
                document.querySelector('.sidebar-overlay')?.classList.remove('active');
                document.body.classList.remove('sidebar-open');
                document.querySelector('.sidebar-toggle-btn')?.setAttribute('aria-expanded', 'false');
            }
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
        '.hero-title',
        '.hero-description',
        '.section-title',
        '.branch-title',
        '.cta-section h2'
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

    // Pause testimonial marquee on touch interaction so users can easily read cards on mobile
    const marqueeWrapper = document.querySelector('.testimonial-marquee-wrapper');
    const marqueeTrack = document.querySelector('.testimonial-track');
    if (marqueeWrapper && marqueeTrack) {
        let touchTimeout;
        marqueeWrapper.addEventListener('touchstart', () => {
            clearTimeout(touchTimeout);
            marqueeWrapper.classList.add('is-paused');
        }, { passive: true });
        
        marqueeWrapper.addEventListener('touchend', () => {
            touchTimeout = setTimeout(() => {
                marqueeWrapper.classList.remove('is-paused');
            }, 1200);
        }, { passive: true });
    }
});
