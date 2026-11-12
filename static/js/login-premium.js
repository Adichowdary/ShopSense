/* ==========================================================================
   ShopSense - Premium Login interactions
   Role selector, floating labels, animated submit, success modal, particles.
   ========================================================================== */
(function () {
    'use strict';

    var STORAGE_KEY = 'shopsense_login_role';

    var ROLE_CONFIG = {
        admin: {
            title: 'Admin Sign In',
            subtitle: 'Access the ShopSense admin dashboard',
            footerHtml: 'Admin accounts are provisioned by the ShopSense team.',
            icon: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"></rect><path d="M8 21h8"></path><path d="M12 17v4"></path></svg>'
        },
        vendor: {
            title: 'Vendor Sign In',
            subtitle: 'Manage your store, products & orders',
            footerHtml: 'Want to sell on ShopSense? <a href="{onboarding}" data-link>Apply to become a vendor</a>',
            icon: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path></svg>'
        },
        customer: {
            title: 'Welcome Back',
            subtitle: 'Sign in to continue shopping on ShopSense',
            footerHtml: "Don't have an account? <a href=\"{register}\" data-link>Create one</a>",
            icon: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>'
        }
    };

    var els = {};
    var currentRole = null;
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    document.addEventListener('DOMContentLoaded', function () {
        cacheElements();
        if (!els.form) return;
        initParticles();
        initFloatingLabels();
        initPasswordToggle();
        initRoleSelector();
        initFormSubmit();
        restoreState();
    });

    function cacheElements() {
        els.config = document.getElementById('loginConfig');
        els.roleSelector = document.getElementById('roleSelector');
        els.loginPanel = document.getElementById('loginPanel');
        els.loginCard = document.getElementById('loginCard');
        els.loginLogo = document.getElementById('loginLogo');
        els.loginTitle = document.getElementById('loginTitle');
        els.loginSubtitle = document.getElementById('loginSubtitle');
        els.backBtn = document.getElementById('backBtn');
        els.form = document.getElementById('loginForm');
        els.submitBtn = document.getElementById('submitBtn');
        els.alertContainer = document.getElementById('alertContainer');
        els.footerText = document.getElementById('footerText');
        els.successModal = document.getElementById('successModal');
        els.successMessage = document.getElementById('successMessage');
        els.passwordToggle = document.getElementById('passwordToggle');
        els.roleOptions = Array.prototype.slice.call(document.querySelectorAll('.role-option'));
        els.fields = {
            username: els.form ? els.form.querySelector('[data-field="username"] .form-input') : null,
            password: els.form ? els.form.querySelector('[data-field="password"] .form-input') : null
        };
    }

    function cfg(name) {
        return els.config ? els.config.getAttribute(name) : '';
    }

    /* ------------------------- Portal / role selector ------------------------- */

    function initRoleSelector() {
        els.roleOptions.forEach(function (btn) {
            btn.addEventListener('click', function () {
                selectRole(btn.getAttribute('data-role'), true);
            });
            btn.addEventListener('keydown', function (e) {
                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                    e.preventDefault();
                    var idx = els.roleOptions.indexOf(btn);
                    var next = e.key === 'ArrowDown'
                        ? (idx + 1) % els.roleOptions.length
                        : (idx - 1 + els.roleOptions.length) % els.roleOptions.length;
                    els.roleOptions[next].focus();
                }
            });
        });

        els.backBtn.addEventListener('click', function () {
            showRoleSelector();
        });
    }

    function selectRole(role, animate) {
        if (!ROLE_CONFIG[role]) role = 'customer';
        currentRole = role;
        try { sessionStorage.setItem(STORAGE_KEY, role); } catch (e) { /* private mode */ }

        els.roleOptions.forEach(function (btn) {
            var active = btn.getAttribute('data-role') === role;
            btn.classList.toggle('is-selected', active);
            btn.setAttribute('aria-checked', active ? 'true' : 'false');
        });

        if (animate && !reduceMotion) {
            els.roleSelector.classList.add('is-leaving');
            window.setTimeout(function () {
                els.roleSelector.hidden = true;
                els.roleSelector.classList.remove('is-leaving');
                showLoginPanel(role, true);
            }, 340);
        } else {
            els.roleSelector.hidden = true;
            showLoginPanel(role, animate);
        }
    }

    function showLoginPanel(role, animate) {
        var conf = ROLE_CONFIG[role] || ROLE_CONFIG.customer;

        els.loginCard.setAttribute('data-role', role);
        els.loginLogo.innerHTML = conf.icon;
        els.loginTitle.textContent = conf.title;
        els.loginSubtitle.textContent = conf.subtitle;

        var footerHtml = conf.footerHtml
            .replace('{register}', cfg('data-register-url'))
            .replace('{onboarding}', cfg('data-onboarding-url'));
        els.footerText.innerHTML = footerHtml;

        els.loginPanel.hidden = false;

        if (animate && !reduceMotion) {
            els.loginPanel.classList.remove('is-entering');
            void els.loginPanel.offsetWidth; /* restart animation */
            els.loginPanel.classList.add('is-entering');
        }

        window.setTimeout(function () {
            if (els.fields.username && els.fields.username.value === '') {
                els.fields.username.focus({ preventScroll: true });
            } else if (els.fields.password) {
                els.fields.password.focus({ preventScroll: true });
            }
        }, animate && !reduceMotion ? 480 : 60);
    }

    function showRoleSelector() {
        try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) { /* ignore */ }
        currentRole = null;
        clearAllErrors();

        if (reduceMotion) {
            els.loginPanel.hidden = true;
            els.roleSelector.hidden = false;
        } else {
            var card = els.loginCard;
            card.style.transition = 'opacity 280ms ease, transform 280ms ease, filter 280ms ease';
            card.style.opacity = '0';
            card.style.transform = 'translateY(12px) scale(0.97)';
            card.style.filter = 'blur(6px)';
            window.setTimeout(function () {
                els.loginPanel.hidden = true;
                card.style.cssText = '';
                els.roleSelector.hidden = false;
                els.roleSelector.style.animation = 'none';
                void els.roleSelector.offsetWidth;
                els.roleSelector.style.animation = '';
                var first = els.roleOptions[0];
                if (first) first.focus({ preventScroll: true });
            }, 280);
        }
    }

    function restoreState() {
        var stored = null;
        try { stored = sessionStorage.getItem(STORAGE_KEY); } catch (e) { /* ignore */ }

        var hasServerErrors = !!(els.alertContainer && els.alertContainer.children.length) ||
            !!(els.fields.username && els.fields.username.parentElement.querySelector('.field-error')) ||
            !!(els.fields.password && els.fields.password.parentElement.querySelector('.field-error'));

        var role = stored || (hasServerErrors ? 'customer' : null);

        if (role) {
            selectRole(role, false);
        }
    }

    /* ---------------------------- Floating labels ---------------------------- */

    function initFloatingLabels() {
        [els.fields.username, els.fields.password].forEach(function (input) {
            if (!input) return;
            var group = input.closest('.form-group');
            var sync = function () {
                group.classList.toggle('filled', input.value.trim() !== '');
            };
            input.addEventListener('input', sync);
            input.addEventListener('change', sync);
            input.addEventListener('blur', sync);
            sync();
        });
    }

    /* --------------------------- Password toggle ---------------------------- */

    function initPasswordToggle() {
        if (!els.passwordToggle || !els.fields.password) return;
        els.passwordToggle.addEventListener('click', function () {
            var input = els.fields.password;
            var showing = input.type === 'text';
            input.type = showing ? 'password' : 'text';
            els.passwordToggle.setAttribute('aria-pressed', showing ? 'false' : 'true');
            els.passwordToggle.setAttribute(
                'aria-label',
                showing ? 'Show password' : 'Hide password'
            );
            input.focus({ preventScroll: true });
        });
    }

    /* ------------------------------ Validation ------------------------------ */

    function validate() {
        var ok = true;
        clearAllErrors();

        var email = els.fields.username;
        var password = els.fields.password;

        if (!email.value.trim()) {
            showFieldError('username', 'Please enter your email address.');
            ok = false;
        } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) {
            showFieldError('username', 'Please enter a valid email address.');
            ok = false;
        }

        if (!password.value) {
            showFieldError('password', 'Please enter your password.');
            ok = false;
        }

        if (!ok) shakeCard();
        return ok;
    }

    function showFieldError(field, message) {
        var group = document.querySelector('[data-field="' + field + '"]');
        if (!group) return;
        var input = group.querySelector('.form-input');
        if (input) input.classList.add('has-error');
        var existing = group.querySelector('.field-error');
        if (existing) existing.remove();
        var err = document.createElement('div');
        err.className = 'field-error';
        err.setAttribute('role', 'alert');
        err.textContent = message;
        group.appendChild(err);
    }

    function clearAllErrors() {
        document.querySelectorAll('.login-card-x .form-input.has-error').forEach(function (i) {
            i.classList.remove('has-error');
        });
        document.querySelectorAll('.login-card-x .field-error').forEach(function (e) {
            e.remove();
        });
        if (els.alertContainer) els.alertContainer.innerHTML = '';
    }

    function shakeCard() {
        if (reduceMotion) return;
        els.loginCard.classList.remove('shake');
        void els.loginCard.offsetWidth;
        els.loginCard.classList.add('shake');
        window.setTimeout(function () {
            els.loginCard.classList.remove('shake');
        }, 520);
    }

    /* ---------------------------- Form submission ---------------------------- */

    function initFormSubmit() {
        els.form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (!validate()) return;

            setLoading(true);

            var actionUrl = els.form.getAttribute('action') || window.location.pathname;

            fetch(actionUrl, {
                method: 'POST',
                body: new FormData(els.form),
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            }).then(function (res) {
                var resUrl;
                try {
                    resUrl = new URL(res.url, window.location.origin);
                } catch (err) {
                    window.location.assign(actionUrl);
                    return;
                }

                var loginPath = cfg('data-login-url') || window.location.pathname;
                var backOnLogin = resUrl.pathname === loginPath;

                if (backOnLogin && res.ok) {
                    /* Invalid credentials - Django re-rendered the login page */
                    return res.text().then(function (html) {
                        applyServerErrors(html);
                        setLoading(false);
                    });
                }

                if (res.ok) {
                    /* Success - show modal, then follow the redirect target */
                    showSuccess(resUrl.pathname);
                    window.setTimeout(function () {
                        window.location.assign(res.url);
                    }, reduceMotion ? 500 : 1500);
                } else if (res.status === 403) {
                    showAlert('Security token expired or session desynchronized. Please refresh the page and try again.');
                    setLoading(false);
                } else if (res.status >= 400 && res.status < 500) {
                    return res.text().then(function (html) {
                        applyServerErrors(html);
                        setLoading(false);
                    });
                } else {
                    showAlert('Something went wrong on our side. Please try again in a moment.');
                    setLoading(false);
                }
            }).catch(function () {
                /* Network failure: fall back to a native submit */
                HTMLFormElement.prototype.submit.call(els.form);
            });
        });
    }

    function applyServerErrors(html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');

        /* Non-field errors */
        var serverAlerts = doc.querySelector('#alertContainer');
        if (els.alertContainer) {
            els.alertContainer.innerHTML = serverAlerts ? serverAlerts.innerHTML : '';
        }

        /* Per-field errors */
        var anyFieldError = false;
        ['username', 'password'].forEach(function (field) {
            var group = document.querySelector('[data-field="' + field + '"]');
            if (!group) return;
            var input = group.querySelector('.form-input');
            var existing = group.querySelector('.field-error');
            if (existing) existing.remove();

            var serverGroup = doc.querySelector('[data-field="' + field + '"]');
            var serverError = serverGroup ? serverGroup.querySelector('.field-error') : null;

            if (serverError) {
                anyFieldError = true;
                if (input) input.classList.add('has-error');
                var clone = serverError.cloneNode(true);
                clone.setAttribute('role', 'alert');
                group.appendChild(clone);
            }
        });

        /* If nothing was parsed (unexpected response), show a generic alert */
        if (!anyFieldError && (!els.alertContainer || !els.alertContainer.children.length)) {
            showAlert('Invalid email or password. Please check your credentials and try again.');
        }

        shakeCard();
    }

    function showAlert(message) {
        if (!els.alertContainer) return;
        els.alertContainer.innerHTML = '';
        var alert = document.createElement('div');
        alert.className = 'alert alert-error';
        alert.innerHTML =
            '<svg class="alert-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" ' +
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<circle cx="12" cy="12" r="10"></circle>' +
            '<line x1="12" y1="8" x2="12" y2="12"></line>' +
            '<line x1="12" y1="16" x2="12.01" y2="16"></line></svg>' +
            '<div class="alert-content"><p class="alert-message"></p></div>';
        alert.querySelector('.alert-message').textContent = message;
        els.alertContainer.appendChild(alert);
        shakeCard();
    }

    function setLoading(loading) {
        els.submitBtn.classList.toggle('is-loading', loading);
        els.submitBtn.disabled = loading;
        els.form.setAttribute('aria-busy', loading ? 'true' : 'false');
    }

    /* ------------------------------ Success modal ---------------------------- */

    function showSuccess(path) {
        if (!els.successModal) return;

        var messages = {
            '/': 'Taking you to the admin dashboard...',
            '/accounts/profile/': 'Taking you to your profile...'
        };
        if (els.successMessage) {
            els.successMessage.textContent = messages[path] || 'Taking you to your dashboard...';
        }

        els.successModal.hidden = false;

        /* Focus trap: keep tab inside the modal */
        els.successModal.addEventListener('keydown', trapFocus);
    }

    function trapFocus(e) {
        if (e.key === 'Escape') e.preventDefault();
        if (e.key === 'Tab') e.preventDefault();
    }

    /* -------------------------------- Particles ------------------------------ */

    function initParticles() {
        var canvas = document.getElementById('particleCanvas');
        if (!canvas || reduceMotion) return;

        var ctx = canvas.getContext('2d');
        if (!ctx) return;

        var particles = [];
        var count = 42;
        var colors = ['rgba(129,140,248,', 'rgba(167,139,250,', 'rgba(103,232,249,'];
        var rafId = null;
        var running = true;

        function resize() {
            var dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = window.innerWidth * dpr;
            canvas.height = window.innerHeight * dpr;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }

        function spawn() {
            particles = [];
            for (var i = 0; i < count; i++) {
                particles.push({
                    x: Math.random() * window.innerWidth,
                    y: Math.random() * window.innerHeight,
                    r: Math.random() * 2 + 0.6,
                    vx: (Math.random() - 0.5) * 0.25,
                    vy: -(Math.random() * 0.22 + 0.05),
                    a: Math.random() * 0.4 + 0.12,
                    color: colors[i % colors.length],
                    phase: Math.random() * Math.PI * 2,
                    wobble: Math.random() * 0.4 + 0.15
                });
            }
        }

        function draw() {
            if (!running) return;
            ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
            var t = Date.now() * 0.001;

            for (var i = 0; i < particles.length; i++) {
                var p = particles[i];
                p.phase += 0.008;
                p.x += p.vx + Math.sin(p.phase) * p.wobble;
                p.y += p.vy;

                if (p.y < -10) { p.y = window.innerHeight + 10; p.x = Math.random() * window.innerWidth; }
                if (p.x < -10) p.x = window.innerWidth + 10;
                if (p.x > window.innerWidth + 10) p.x = -10;

                var twinkle = p.a + Math.sin(t * 1.4 + i) * 0.08;
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                ctx.fillStyle = p.color + Math.max(0.05, twinkle).toFixed(3) + ')';
                ctx.fill();
            }

            rafId = window.requestAnimationFrame(draw);
        }

        resize();
        spawn();
        draw();

        window.addEventListener('resize', function () {
            resize();
        });

        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                running = false;
                if (rafId) window.cancelAnimationFrame(rafId);
            } else {
                running = true;
                draw();
            }
        });
    }
})();
