document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    if(typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // Mobile Menu Toggle
    const menuBtn = document.querySelector('.mobile-menu-btn');
    const nav = document.querySelector('.main-nav');
    
    if(menuBtn && nav) {
        menuBtn.addEventListener('click', () => {
            nav.classList.toggle('active');
        });
    }
});
