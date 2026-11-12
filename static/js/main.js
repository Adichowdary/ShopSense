/**
 * ShopSense - Enhanced Main JavaScript
 * Common utilities, interactions, and UI enhancements
 */

(function() {
    'use strict';

    // ===== Global State =====
    const state = {
        toasts: [],
        sidebarOpen: false,
        sidebarCollapsed: false,
    };

    // ===== Utility Functions =====
    const $ = (selector, context = document) => context.querySelector(selector);
    const $$ = (selector, context = document) => Array.from(context.querySelectorAll(selector));

    const createElement = (html) => {
        const template = document.createElement('template');
        template.innerHTML = html.trim();
        return template.content.firstElementChild;
    };

    const debounce = (fn, delay) => {
        let timeoutId;
        return (...args) => {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => fn(...args), delay);
        };
    };

    const throttle = (fn, limit) => {
        let inThrottle;
        return (...args) => {
            if (!inThrottle) {
                fn(...args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    };

    // ===== Lucide Icons =====
    function initLucide() {
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    // ===== Toast Notification System =====
    function initToasts() {
        // Create container if not exists
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
    }

    function showToast(message, options = {}) {
        const {
            type = 'info',
            title = '',
            duration = 5000,
            action = null,
        } = options;

        initToasts();
        const container = document.getElementById('toast-container');

        const icons = {
            success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
            error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
            warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
            info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>',
        };

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'polite');
        toast.innerHTML = `
            <div class="toast-icon" style="color: var(--color-${type}-500);">${icons[type]}</div>
            <div class="toast-content">
                ${title ? `<div class="toast-title">${title}</div>` : ''}
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close" aria-label="Dismiss">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
            ${action ? `<button class="toast-action btn btn-sm btn-ghost">${action.label}</button>` : ''}
        `;

        container.appendChild(toast);
        initLucide();

        // Animate in
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        // Auto dismiss
        let timeoutId;
        if (duration > 0) {
            timeoutId = setTimeout(() => dismissToast(toast), duration);
        }

        // Manual dismiss
        toast.querySelector('.toast-close').addEventListener('click', () => {
            if (timeoutId) clearTimeout(timeoutId);
            dismissToast(toast);
        });

        // Action button
        if (action && action.onClick) {
            toast.querySelector('.toast-action').addEventListener('click', () => {
                if (timeoutId) clearTimeout(timeoutId);
                action.onClick();
                dismissToast(toast);
            });
        }

        return toast;
    }

    function dismissToast(toast) {
        toast.classList.add('hiding');
        toast.classList.remove('show');
        toast.addEventListener('transitionend', () => toast.remove(), { once: true });
    }

    // ===== Form Validation Enhancement =====
    function enhanceFormValidation() {
        const forms = document.querySelectorAll('form[novalidate]');

        forms.forEach(form => {
            const inputs = form.querySelectorAll('input, select, textarea');

            inputs.forEach(input => {
                // Add validation classes on blur
                input.addEventListener('blur', function() {
                    if (this.checkValidity()) {
                        this.classList.remove('error');
                        this.classList.add('valid');
                    } else {
                        this.classList.remove('valid');
                        this.classList.add('error');
                    }
                });

                // Clear error on input
                input.addEventListener('input', function() {
                    if (this.classList.contains('error') && this.checkValidity()) {
                        this.classList.remove('error');
                        this.classList.add('valid');
                    }
                });

                // Floating label support
                if (input.closest('.form-floating')) {
                    const updateLabel = () => {
                        const label = input.closest('.form-floating').querySelector('label');
                        if (label) {
                            label.style.opacity = input.value ? '1' : '0';
                        }
                    };
                    input.addEventListener('input', updateLabel);
                    input.addEventListener('focus', updateLabel);
                    input.addEventListener('blur', updateLabel);
                    updateLabel();
                }
            });

            // Prevent submission if invalid
            form.addEventListener('submit', function(e) {
                if (!this.checkValidity()) {
                    e.preventDefault();
                    const firstInvalid = this.querySelector(':invalid');
                    if (firstInvalid) {
                        firstInvalid.focus();
                        firstInvalid.classList.add('error');
                        showToast('Please fix the errors in the form', { type: 'error' });
                    }
                }
            });
        });
    }

    // ===== Table Enhancements =====
    function enhanceTables() {
        // Row click handler
        document.querySelectorAll('table[data-row-link]').forEach(table => {
            table.querySelectorAll('tbody tr').forEach(row => {
                const link = row.dataset.href || row.querySelector('a[data-row-action]')?.href;
                if (link) {
                    row.style.cursor = 'pointer';
                    row.addEventListener('click', (e) => {
                        if (!e.target.closest('a, button, input, select, .table-row-action')) {
                            window.location.href = link;
                        }
                    });
                }
            });
        });

        // Sortable headers
        document.querySelectorAll('table th.sortable').forEach(th => {
            th.style.cursor = 'pointer';
            th.addEventListener('click', function() {
                const table = this.closest('table');
                const column = this.cellIndex;
                const isAsc = this.classList.contains('sorted-asc');
                const isDesc = this.classList.contains('sorted-desc');

                // Remove sort classes from all headers
                table.querySelectorAll('th').forEach(h => {
                    h.classList.remove('sorted-asc', 'sorted-desc');
                });

                // Toggle sort direction
                if (isAsc) {
                    this.classList.add('sorted-desc');
                } else {
                    this.classList.add('sorted-asc');
                }

                // Sort rows
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const direction = isAsc ? -1 : 1;

                rows.sort((a, b) => {
                    const aVal = a.cells[column].textContent.trim();
                    const bVal = b.cells[column].textContent.trim();

                    // Try numeric comparison
                    const aNum = parseFloat(aVal.replace(/[^\d.-]/g, ''));
                    const bNum = parseFloat(bVal.replace(/[^\d.-]/g, ''));

                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        return (aNum - bNum) * direction;
                    }

                    return aVal.localeCompare(bVal) * direction;
                });

                rows.forEach(row => tbody.appendChild(row));
            });
        });
    }

    // ===== Confirmation Dialogs =====
    function enableConfirmActions() {
        document.querySelectorAll('[data-confirm]').forEach(element => {
            element.addEventListener('click', function(e) {
                const message = this.dataset.confirm;
                if (!confirm(message)) {
                    e.preventDefault();
                }
            });
        });
    }

    // ===== Copy to Clipboard =====
    function enableCopyToClipboard() {
        document.querySelectorAll('[data-copy]').forEach(element => {
            element.addEventListener('click', async function() {
                const text = this.dataset.copy;
                try {
                    await navigator.clipboard.writeText(text);
                    showToast('Copied to clipboard', { type: 'success' });
                } catch (err) {
                    showToast('Failed to copy', { type: 'error' });
                }
            });
        });
    }

    // ===== Password Toggle =====
    function initPasswordToggles() {
        document.querySelectorAll('.password-toggle').forEach(btn => {
            btn.addEventListener('click', function() {
                const input = this.closest('.password-wrapper').querySelector('input');
                const icon = this.querySelector('svg');
                if (input.type === 'password') {
                    input.type = 'text';
                    icon.setAttribute('data-lucide', 'eye-off');
                } else {
                    input.type = 'password';
                    icon.setAttribute('data-lucide', 'eye');
                }
                initLucide();
            });
        });
    }

    // ===== Sidebar Toggle =====
    function initSidebar() {
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        const mobileMenuToggle = document.getElementById('mobileMenuToggle');
        const sidebarCollapseBtn = document.getElementById('sidebarCollapseBtn');
        const mainContent = document.getElementById('mainContent');

        // Mobile menu
        if (mobileMenuToggle && sidebar && sidebarOverlay) {
            mobileMenuToggle.addEventListener('click', function() {
                const isOpen = sidebar.classList.toggle('open');
                sidebarOverlay.classList.toggle('show', isOpen);
                mobileMenuToggle.setAttribute('aria-expanded', isOpen);
                state.sidebarOpen = isOpen;

                const icon = this.querySelector('i');
                if (icon) {
                    icon.setAttribute('data-lucide', isOpen ? 'x' : 'menu');
                }
                initLucide();
            });

            sidebarOverlay.addEventListener('click', function() {
                sidebar.classList.remove('open');
                sidebarOverlay.classList.remove('show');
                mobileMenuToggle.setAttribute('aria-expanded', 'false');
                state.sidebarOpen = false;

                const icon = mobileMenuToggle.querySelector('i');
                if (icon) {
                    icon.setAttribute('data-lucide', 'menu');
                }
                initLucide();
            });
        }

        // Sidebar collapse (desktop)
        if (sidebarCollapseBtn && sidebar) {
            sidebarCollapseBtn.addEventListener('click', function() {
                const isCollapsed = sidebar.classList.toggle('collapsed');
                sidebarCollapseBtn.setAttribute('aria-expanded', !isCollapsed);
                state.sidebarCollapsed = isCollapsed;

                const icon = this.querySelector('i');
                if (icon) {
                    icon.setAttribute('data-lucide', isCollapsed ? 'chevron-right' : 'chevron-left');
                }
                initLucide();
            });
        }

        // Keyboard navigation for sidebar
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && sidebar.classList.contains('open')) {
                sidebar.classList.remove('open');
                sidebarOverlay.classList.remove('show');
                mobileMenuToggle.setAttribute('aria-expanded', 'false');
                state.sidebarOpen = false;

                const icon = mobileMenuToggle.querySelector('i');
                if (icon) {
                    icon.setAttribute('data-lucide', 'menu');
                }
                initLucide();
            }

            // Toggle sidebar with Ctrl+B
            if (e.ctrlKey && e.key === 'b') {
                e.preventDefault();
                if (sidebarCollapseBtn) sidebarCollapseBtn.click();
            }

            // Focus search with Ctrl+K
            if (e.ctrlKey && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.querySelector('.header-search-input');
                if (searchInput) searchInput.focus();
            }
        });
    }

    // ===== User Menu Dropdown =====
    function initUserMenu() {
        const dropdown = document.querySelector('.user-menu-dropdown');
        if (!dropdown) return;

        const trigger = dropdown.querySelector('.user-menu-trigger');
        const panel = dropdown.querySelector('.user-menu-panel');

        if (trigger) {
            trigger.addEventListener('click', function(e) {
                e.stopPropagation();
                dropdown.classList.toggle('open');
            });
        }

        // Close on outside click
        document.addEventListener('click', function(e) {
            if (dropdown.classList.contains('open') && !dropdown.contains(e.target)) {
                dropdown.classList.remove('open');
            }
        });

        // Close on Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && dropdown.classList.contains('open')) {
                dropdown.classList.remove('open');
            }
        });
    }

    // ===== Theme Toggle =====
    function initThemeToggle() {
        const toggle = document.getElementById('theme-toggle');
        if (!toggle) return;

        // Check saved theme
        const savedTheme = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const initialTheme = savedTheme || (prefersDark ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', initialTheme);
        updateThemeIcon(initialTheme);

        toggle.addEventListener('click', function() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = toggle.querySelector('i');
            if (icon) {
                icon.setAttribute('data-lucide', theme === 'dark' ? 'sun' : 'moon');
            }
            initLucide();
        }
    }

    // ===== Search Enhancement =====
    function initSearch() {
        const searchInput = document.querySelector('.header-search-input');
        if (!searchInput) return;

        // Show search on focus
        searchInput.addEventListener('focus', function() {
            this.style.width = '380px';
        });

        searchInput.addEventListener('blur', function() {
            if (!this.value) {
                this.style.width = '';
            }
        });

        // Keyboard shortcut
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                searchInput.focus();
            }
        });
    }

    // ===== Initialize All =====
    function init() {
        initLucide();
        enhanceFormValidation();
        enhanceTables();
        enableConfirmActions();
        enableCopyToClipboard();
        initPasswordToggles();
        initSidebar();
        initUserMenu();
        initThemeToggle();
        initSearch();
        initModalFocus();

        // Re-initialize Lucide on dynamic content
        const observer = new MutationObserver(debounce(initLucide, 100));
        observer.observe(document.body, { childList: true, subtree: true });
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // ===== Modal Focus Management =====
    function initModalFocus() {
        const focusableSelectors = [
            'a[href]',
            'button:not([disabled])',
            'input:not([disabled])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            '[tabindex]:not([tabindex="-1"])',
        ].join(', ');

        function trapFocus(modal) {
            const focusable = modal.querySelectorAll(focusableSelectors);
            const first = focusable[0];
            const last = focusable[focusable.length - 1];

            if (first) first.focus({ preventScroll: true });

            modal.addEventListener('keydown', function handleKeydown(e) {
                if (e.key === 'Tab') {
                    if (e.shiftKey) {
                        if (document.activeElement === first) {
                            e.preventDefault();
                            last.focus({ preventScroll: true });
                        }
                    } else {
                        if (document.activeElement === last) {
                            e.preventDefault();
                            first.focus({ preventScroll: true });
                        }
                    }
                }
                if (e.key === 'Escape') {
                    const closeBtn = modal.querySelector('.modal-close, [data-modal-close]');
                    if (closeBtn) closeBtn.click();
                }
            });
        }

        // Expose globally for other scripts (e.g., login-premium.js)
        window.ShopSense.trapFocus = trapFocus;
    }
    window.ShopSense = {
        showToast,
        dismissToast,
        initLucide,
        debounce,
        throttle,
        $,
        $$,
    };
})();