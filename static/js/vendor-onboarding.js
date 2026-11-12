/**
 * ShopSense - Vendor Onboarding Wizard
 * Multi-step form with validation, autosave, file uploads, and review
 */

(function() {
    'use strict';

    // ===== Configuration =====
    const STEPS = 3;
    const STORAGE_KEY = 'shopsense_vendor_draft';
    const AUTOSAVE_DELAY = 1500;

    // ===== State =====
    let currentStep = 1;
    let formData = {};
    let draftTimer = null;
    let isSubmitting = false;

    // ===== DOM Elements =====
    const els = {};
    const form = document.getElementById('onboardingForm');

    function cacheElements() {
        els.steps = Array.from(document.querySelectorAll('.form-step'));
        els.progressSteps = Array.from(document.querySelectorAll('.progress-step'));
        els.progressFill = document.getElementById('progressFill');
        els.mobileProgressFill = document.getElementById('mobileProgressFill');
        els.mobileStepNum = document.getElementById('mobileStepNum');
        els.mobileProgressFill = document.getElementById('mobileProgressFill');
        els.stepTitle = document.getElementById('stepTitle');
        els.stepDescription = document.getElementById('stepDescription');
        els.currentStepNum = document.getElementById('currentStepNum');
        els.mobileStepNum = document.getElementById('mobileStepNum');
        els.prevBtn = document.getElementById('prevBtn');
        els.nextBtn = document.getElementById('nextBtn');
        els.submitBtn = document.getElementById('submitBtn');
        els.saveDraftBtn = document.getElementById('saveDraftBtn');
        els.draftStatus = document.getElementById('draftStatus');
        els.alertContainer = document.getElementById('alertContainer');
        els.reviewContent = document.getElementById('reviewContent');
        els.termsAgreed = document.getElementById('termsAgreed');
        els.successModal = document.getElementById('successModal');
        els.exitModal = document.getElementById('exitModal');
        els.stayBtn = document.getElementById('stayBtn');
        els.leaveBtn = document.getElementById('leaveBtn');
        // File uploads
        els.logoInput = form.querySelector('[name="logo"]');
        els.bannerInput = form.querySelector('[name="banner"]');
        els.logoPlaceholder = document.getElementById('logoPlaceholder');
        els.bannerPlaceholder = document.getElementById('bannerPlaceholder');
        els.logoPreview = document.getElementById('logoPreview');
        els.bannerPreview = document.getElementById('bannerPreview');
    }

    // ===== Step Configuration =====
    const STEP_CONFIG = {
        1: {
            title: 'Business Information',
            description: 'Tell us about your business to get started',
            fields: ['business_name', 'business_description', 'website', 'tax_id', 'logo', 'banner']
        },
        2: {
            title: 'Contact & Address',
            description: 'Where can we reach you and where is your business located?',
            fields: ['contact_email', 'contact_phone', 'business_address', 'city', 'state', 'postal_code', 'country']
        },
        3: {
            title: 'Review & Submit',
            description: 'Verify your information and submit your application',
            fields: []
        }
    };

    // ===== Initialization =====
    document.addEventListener('DOMContentLoaded', function() {
        cacheElements();
        if (!form) return;

        loadDraft();
        initFileUploads();
        initFormValidation();
        initNavigation();
        initAutosave();
        initExitIntent();
        initLucide();
        updateUI();

        // Restore step if draft has data beyond step 1
        if (formData.currentStep) {
            currentStep = Math.min(formData.currentStep, STEPS);
            goToStep(currentStep, false);
        }
    });

    // ===== Lucide Icons =====
    function initLucide() {
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    // ===== Form Data Management =====
    function collectFormData() {
        const data = {};
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            if (input.type === 'file') {
                // Files can't be stored in localStorage, skip
                return;
            }
            if (input.type === 'checkbox' || input.type === 'radio') {
                data[input.name] = input.checked;
            } else {
                data[input.name] = input.value;
            }
        });
        data.currentStep = currentStep;
        data.timestamp = Date.now();
        return data;
    }

    function populateForm(data) {
        if (!data) return;
        Object.keys(data).forEach(key => {
            if (key === 'currentStep' || key === 'timestamp') return;
            const input = form.querySelector('[name="' + key + '"]');
            if (!input) return;
            if (input.type === 'checkbox' || input.type === 'radio') {
                input.checked = data[key];
                input.dispatchEvent(new Event('change'));
            } else if (input.tagName === 'SELECT') {
                input.value = data[key];
            } else {
                input.value = data[key];
            }
        });
    }

    function loadDraft() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                const data = JSON.parse(saved);
                // Only load if draft is less than 7 days old
                if (Date.now() - data.timestamp < 7 * 24 * 60 * 60 * 1000) {
                    formData = data;
                    populateForm(data);
                    showDraftStatus('Draft restored from ' + new Date(data.timestamp).toLocaleString());
                }
            }
        } catch (e) {
            console.warn('Failed to load draft:', e);
        }
    }

    function saveDraft(silent = false) {
        try {
            formData = collectFormData();
            localStorage.setItem(STORAGE_KEY, JSON.stringify(formData));
            if (!silent) {
                showDraftStatus('Draft saved at ' + new Date().toLocaleTimeString());
            }
        } catch (e) {
            console.warn('Failed to save draft:', e);
        }
    }

    function clearDraft() {
        try {
            localStorage.removeItem(STORAGE_KEY);
            formData = {};
        } catch (e) {
            console.warn('Failed to clear draft:', e);
        }
    }

    function showDraftStatus(message) {
        if (els.draftStatus) {
            els.draftStatus.textContent = message;
            els.draftStatus.style.color = 'var(--color-success-600)';
            clearTimeout(els.draftStatus._timer);
            els.draftStatus._timer = setTimeout(() => {
                els.draftStatus.textContent = '';
            }, 3000);
        }
    }

    // ===== File Upload Handling =====
    function initFileUploads() {
        // Logo
        if (els.logoInput) {
            els.logoInput.addEventListener('change', function(e) {
                handleFileSelect(e, 'logo');
            });
        }
        // Banner
        if (els.bannerInput) {
            els.bannerInput.addEventListener('change', function(e) {
                handleFileSelect(e, 'banner');
            });
        }

        // Click to upload
        ['logo', 'banner'].forEach(type => {
            const placeholder = document.getElementById(type + 'Placeholder');
            const input = document.querySelector('[name="' + type + '"]');
            if (placeholder && input) {
                placeholder.addEventListener('click', () => input.click());
                placeholder.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        input.click();
                    }
                });
                placeholder.setAttribute('tabindex', '0');
                placeholder.setAttribute('role', 'button');
                placeholder.setAttribute('aria-label', 'Upload ' + type);
            }

            // Remove button
            const removeBtn = document.querySelector('[data-target="' + type + '"]');
            if (removeBtn) {
                removeBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    removeFile(type);
                });
            }
        });
    }

    function handleFileSelect(e, type) {
        const file = e.target.files[0];
        if (!file) return;

        // Validate file
        if (!file.type.startsWith('image/')) {
            showAlert('Please select an image file (PNG, JPG, WebP)', 'error');
            e.target.value = '';
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            showAlert('File size must be less than 5MB', 'error');
            e.target.value = '';
            return;
        }

        // Show preview
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById(type + 'Preview');
            const placeholder = document.getElementById(type + 'Placeholder');
            if (preview && placeholder) {
                preview.querySelector('img').src = e.target.result;
                placeholder.hidden = true;
                preview.hidden = false;
            }
        };
        reader.readAsDataURL(file);

        // Trigger autosave
        scheduleAutosave();
    }

    function removeFile(type) {
        const input = document.querySelector('[name="' + type + '"]');
        const preview = document.getElementById(type + 'Preview');
        const placeholder = document.getElementById(type + 'Placeholder');
        if (input) input.value = '';
        if (preview) preview.hidden = true;
        if (placeholder) placeholder.hidden = false;
        scheduleAutosave();
    }

    // ===== Form Validation =====
    function initFormValidation() {
        const inputs = form.querySelectorAll('input, select, textarea');

        inputs.forEach(input => {
            // Real-time validation on blur
            input.addEventListener('blur', function() {
                validateField(this);
            });

            // Clear error on input
            input.addEventListener('input', function() {
                if (this.classList.contains('error')) {
                    validateField(this);
                }
                scheduleAutosave();
            });

            // Checkbox change
            if (input.type === 'checkbox') {
                input.addEventListener('change', function() {
                    scheduleAutosave();
                    if (this.id === 'termsAgreed') {
                        updateSubmitButton();
                    }
                });
            }
        });

        // Form submit
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            if (validateCurrentStep()) {
                submitForm();
            }
        });
    }

    function validateField(input) {
        const isValid = input.checkValidity();
        const group = input.closest('.form-group');

        if (isValid) {
            input.classList.remove('error');
            input.classList.add('valid');
            if (group) {
                const error = group.querySelector('.form-error');
                if (error) error.remove();
            }
        } else {
            input.classList.remove('valid');
            input.classList.add('error');
            if (group) {
                // Remove existing error
                const existing = group.querySelector('.form-error');
                if (existing) existing.remove();
                // Add new error
                const error = document.createElement('div');
                error.className = 'form-error';
                error.setAttribute('role', 'alert');
                error.textContent = input.validationMessage || 'This field is required';
                group.appendChild(error);
            }
        }
        return isValid;
    }

    function validateStep(step) {
        const stepEl = document.querySelector('.form-step[data-step="' + step + '"]');
        if (!stepEl) return true;

        const requiredInputs = stepEl.querySelectorAll('input[required], select[required], textarea[required]');
        let isValid = true;

        requiredInputs.forEach(input => {
            if (!validateField(input)) {
                isValid = false;
            }
        });

        // Special validation for step 3
        if (step === 3) {
            if (!els.termsAgreed.checked) {
                showAlert('You must agree to the Terms of Service and Privacy Policy', 'error');
                isValid = false;
            }
        }

        // Update step indicator
        const stepIndicator = document.querySelector('.progress-step[data-step="' + step + '"]');
        if (stepIndicator) {
            stepIndicator.classList.toggle('has-error', !isValid);
        }

        return isValid;
    }

    function validateCurrentStep() {
        return validateStep(currentStep);
    }

    function updateSubmitButton() {
        if (els.submitBtn && els.termsAgreed) {
            els.submitBtn.disabled = !els.termsAgreed.checked;
        }
    }

    // ===== Navigation =====
    function initNavigation() {
        // Next button
        els.nextBtn.addEventListener('click', function() {
            if (validateCurrentStep()) {
                goToStep(currentStep + 1);
            }
        });

        // Previous button
        els.prevBtn.addEventListener('click', function() {
            goToStep(currentStep - 1);
        });

        // Progress step clicks (desktop)
        document.querySelectorAll('.progress-step button[data-step]').forEach(btn => {
            btn.addEventListener('click', function() {
                const step = parseInt(this.getAttribute('data-step'), 10);
                if (step < currentStep || step === currentStep + 1) {
                    if (validateCurrentStep() || step < currentStep) {
                        goToStep(step);
                    }
                }
            });
        });

        // Save draft
        els.saveDraftBtn.addEventListener('click', function() {
            saveDraft(false);
        });
    }

    function goToStep(step, animate = true) {
        if (step < 1 || step > STEPS) return;

        // Hide current step
        const currentEl = document.querySelector('.form-step[data-step="' + currentStep + '"]');
        if (currentEl) {
            currentEl.hidden = true;
        }

        // Show new step
        const newEl = document.querySelector('.form-step[data-step="' + step + '"]');
        if (newEl) {
            newEl.hidden = false;
            if (animate) {
                newEl.style.animation = 'none';
                void newEl.offsetWidth; // trigger reflow
                newEl.style.animation = '';
            }
        }

        currentStep = step;
        updateUI();

        // Build review on step 3
        if (step === 3) {
            buildReview();
        }

        // Scroll to top of form
        const formWrapper = document.querySelector('.onboarding-form-wrapper');
        if (formWrapper) {
            formWrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    function updateUI() {
        // Update step config
        const config = STEP_CONFIG[currentStep];
        if (config) {
            if (els.stepTitle) els.stepTitle.textContent = config.title;
            if (els.stepDescription) els.stepDescription.textContent = config.description;
            if (els.currentStepNum) els.currentStepNum.textContent = currentStep;
            if (els.mobileStepNum) els.mobileStepNum.textContent = currentStep;
        }

        // Progress bar
        const progress = (currentStep / STEPS) * 100;
        if (els.progressFill) els.progressFill.style.width = progress + '%';
        if (els.mobileProgressFill) els.mobileProgressFill.style.width = progress + '%';

        // Step indicators
        els.progressSteps.forEach((stepEl, index) => {
            const stepNum = index + 1;
            stepEl.classList.toggle('active', stepNum === currentStep);
            stepEl.classList.toggle('completed', stepNum < currentStep);
        });

        if (els.mobileStepNum) {
            els.mobileStepNum.textContent = currentStep;
        }

        // Navigation buttons
        if (els.prevBtn) els.prevBtn.hidden = currentStep === 1;
        if (els.nextBtn) els.nextBtn.hidden = currentStep === STEPS;
        if (els.submitBtn) els.submitBtn.hidden = currentStep !== STEPS;

        // Update progress steps
        els.progressSteps.forEach((stepEl, index) => {
            const stepNum = index + 1;
            stepEl.classList.toggle('active', stepNum === currentStep);
            stepEl.classList.toggle('completed', stepNum < currentStep);
            const btn = stepEl.querySelector('button');
            if (btn) {
                btn.disabled = stepNum > currentStep + 1;
            }
        });

        // Mobile progress
        const mobileProgress = (currentStep / STEPS) * 100;
        if (els.mobileProgressFill) els.mobileProgressFill.style.width = mobileProgress + '%';
        if (els.mobileStepNum) els.mobileStepNum.textContent = currentStep;

        // Update submit button state
        updateSubmitButton();

        // Focus first invalid or first input
        setTimeout(() => {
            const stepEl = document.querySelector('.form-step[data-step="' + currentStep + '"]');
            if (stepEl) {
                const firstInput = stepEl.querySelector('input:not([type="hidden"]), select, textarea');
                if (firstInput) firstInput.focus({ preventScroll: true });
            }
        }, 100);
    }

    // ===== Review Builder =====
    function buildReview() {
        if (!els.reviewContent) return;

        const sections = [
            {
                key: 'business',
                title: 'Business Information',
                fields: [
                    { key: 'business_name', label: 'Business Name' },
                    { key: 'business_description', label: 'Description' },
                    { key: 'website', label: 'Website' },
                    { key: 'tax_id', label: 'Tax ID (GST/PAN)' }
                ]
            },
            {
                key: 'contact',
                title: 'Contact & Address',
                fields: [
                    { key: 'contact_email', label: 'Email' },
                    { key: 'contact_phone', label: 'Phone' },
                    { key: 'business_address', label: 'Address' },
                    { key: 'city', label: 'City' },
                    { key: 'state', label: 'State' },
                    { key: 'postal_code', label: 'Postal Code' },
                    { key: 'country', label: 'Country' }
                ]
            },
            {
                key: 'brand',
                title: 'Brand Assets',
                fields: [
                    { key: 'logo', label: 'Logo', isFile: true },
                    { key: 'banner', label: 'Banner', isFile: true }
                ]
            }
        ];

        let html = '';
        sections.forEach(section => {
            const hasData = section.fields.some(f => {
                const val = formData[f.key];
                return val && (f.isFile ? val : val.trim());
            });

            if (!hasData) return;

            html += '<div class="review-card">';
            html += '<div class="review-card-header">';
            html += '<h4 class="review-card-title">' + section.title + '</h4>';
            html += '<button type="button" class="edit-step-btn" data-step="' + (section.key === 'business' ? 1 : section.key === 'contact' ? 2 : 3) + '">';
            html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5a2.121 2.121 0 0 1 3 3z"></path></svg>';
            html += ' Edit</button>';
            html += '</div>';
            html += '<div class="review-grid">';

            section.fields.forEach(field => {
                const val = formData[field.key];
                const displayVal = field.isFile
                    ? (val ? '<span class="review-value">File selected</span>' : '<span class="review-value empty">Not provided</span>')
                    : (val && val.trim() ? '<span class="review-value">' + escapeHtml(val) + '</span>' : '<span class="review-value empty">Not provided</span>');

                html += '<div class="review-item">';
                html += '<span class="review-label">' + field.label + '</span>';
                html += displayVal;
                html += '</div>';
            });

            html += '</div></div>';
        });

        // Add logo/banner previews if available
        const logoFile = form.querySelector('[name="logo"]').files[0];
        const bannerFile = form.querySelector('[name="banner"]').files[0];

        if (logoFile || formData.logo) {
            // Logo preview already shown in file upload area
        }

        if (els.reviewContent) {
            els.reviewContent.innerHTML = html;

            // Bind edit buttons
            els.reviewContent.querySelectorAll('.edit-step-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const step = parseInt(this.getAttribute('data-step'), 10);
                    goToStep(step);
                });
            });
        }
    }

    // ===== Autosave =====
    function initAutosave() {
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('input', scheduleAutosave);
            input.addEventListener('change', scheduleAutosave);
        });
    }

    function scheduleAutosave() {
        clearTimeout(draftTimer);
        draftTimer = setTimeout(() => {
            saveDraft(true);
        }, AUTOSAVE_DELAY);
    }

    // ===== Exit Intent =====
    function initExitIntent() {
        let hasInteracted = false;

        form.addEventListener('input', () => { hasInteracted = true; });
        form.addEventListener('change', () => { hasInteracted = true; });

        window.addEventListener('beforeunload', function(e) {
            if (hasInteracted && !isSubmitting) {
                saveDraft(true);
                e.preventDefault();
                e.returnValue = '';
            }
        });

        // Exit intent detection (mouse leaving viewport)
        document.addEventListener('mouseleave', function(e) {
            if (hasInteracted && !isSubmitting && currentStep > 1 && e.clientY <= 0) {
                showExitModal();
            }
        });
    }

    function showExitModal() {
        if (els.exitModal) {
            els.exitModal.hidden = false;
            setTimeout(() => els.exitModal.classList.add('show'), 10);
            if (els.stayBtn) els.stayBtn.focus();
        }
    }

    function hideExitModal() {
        if (els.exitModal) {
            els.exitModal.classList.remove('show');
            setTimeout(() => { els.exitModal.hidden = true; }, 200);
        }
    }

    if (els.stayBtn) {
        els.stayBtn.addEventListener('click', hideExitModal);
    }
    if (els.leaveBtn) {
        els.leaveBtn.addEventListener('click', function() {
            saveDraft(true);
            hideExitModal();
            window.location.href = '/';
        });
    }

    // ===== Form Submission =====
    async function submitForm() {
        if (isSubmitting) return;
        isSubmitting = true;

        // Show loading state
        const submitBtn = els.submitBtn;
        const originalHTML = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="loading-spinner" style="width:20px;height:20px;border-width:2px;"></span> Submitting...';

        try {
            const formDataToSubmit = new FormData(form);
            const response = await fetch(form.action || window.location.pathname, {
                method: 'POST',
                body: formDataToSubmit,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCSRFToken()
                },
                credentials: 'same-origin'
            });

            if (response.redirected) {
                // Successful redirect
                window.location.href = response.url;
                return;
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const data = await response.json();
                if (data.success) {
                    showSuccessModal(data);
                    clearDraft();
                } else {
                    showAlert(data.error || 'Submission failed', 'error');
                }
            } else {
                const html = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const alertContainer = doc.querySelector('#alertContainer');
                if (alertContainer && alertContainer.innerHTML) {
                    if (els.alertContainer) {
                        els.alertContainer.innerHTML = alertContainer.innerHTML;
                    }
                    // Check for field errors
                    applyServerErrors(doc);
                    shakeCard();
                } else if (response.ok) {
                    // Success - redirect
                    showSuccessModal({ vendor_id: 'VND' + Date.now().toString(36).toUpperCase(), email: formData.contact_email });
                    clearDraft();
                }
            }
        } catch (err) {
            console.error('Submit error:', err);
            showAlert('Network error. Please try again.', 'error');
        } finally {
            isSubmitting = false;
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalHTML;
        }
    }

    function getCSRFToken() {
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }

    function applyServerErrors(doc) {
        // Apply field errors from server response
        ['business_name', 'business_description', 'website', 'tax_id', 'logo', 'banner',
         'contact_email', 'contact_phone', 'business_address', 'city', 'state', 'postal_code', 'country'].forEach(field => {
            const serverGroup = doc.querySelector('[name="' + field + '"]')?.closest('.form-group');
            const serverError = serverGroup?.querySelector('.form-error');
            const localGroup = document.querySelector('[name="' + field + '"]')?.closest('.form-group');

            if (serverError && localGroup) {
                const existing = localGroup.querySelector('.form-error');
                if (existing) existing.remove();
                const clone = serverError.cloneNode(true);
                clone.setAttribute('role', 'alert');
                localGroup.appendChild(clone);
                const input = localGroup.querySelector('input, select, textarea');
                if (input) input.classList.add('error');
            }
        });
    }

    function shakeCard() {
        const card = document.querySelector('.onboarding-form-wrapper');
        if (card) {
            card.classList.remove('shake');
            void card.offsetWidth;
            card.classList.add('shake');
            setTimeout(() => card.classList.remove('shake'), 500);
        }
    }

    // ===== Success Modal =====
    function showSuccessModal(data) {
        if (!els.successModal) return;

        const message = els.successModal.querySelector('#successMessage');
        if (message && data) {
            message.innerHTML = 'Your vendor application has been received. Your vendor ID is <strong>' + (data.vendor_id || 'VND' + Date.now().toString(36).toUpperCase()) + '</strong>. We\'ll review your application and contact you at <strong>' + (data.email || formData.contact_email) + '</strong> within 3-5 business days.';
        }

        els.successModal.hidden = false;
        setTimeout(() => els.successModal.classList.add('show'), 10);

        // Focus trap
        const focusable = els.successModal.querySelectorAll('button, a');
        const firstFocusable = focusable[0];
        const lastFocusable = focusable[focusable.length - 1];

        els.successModal.addEventListener('keydown', function trapFocus(e) {
            if (e.key === 'Tab') {
                if (e.shiftKey && document.activeElement === firstFocusable) {
                    e.preventDefault();
                    lastFocusable.focus();
                } else if (!e.shiftKey && document.activeElement === lastFocusable) {
                    e.preventDefault();
                    firstFocusable.focus();
                }
            }
        }, { once: true });

        if (firstFocusable) firstFocusable.focus();
    }

    // ===== Alert System =====
    function showAlert(message, type = 'error') {
        if (!els.alertContainer) return;

        const icons = {
            error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
            success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
            warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
            info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
        };

        const alert = document.createElement('div');
        alert.className = 'alert alert-' + type;
        alert.setAttribute('role', 'alert');
        alert.innerHTML = icons[type] + '<div class="alert-content"><p class="alert-message">' + message + '</p></div>';
        alert.style.animation = 'slideInDown 0.3s ease-out';

        els.alertContainer.innerHTML = '';
        els.alertContainer.appendChild(alert);

        // Auto dismiss for non-error
        if (type !== 'error') {
            setTimeout(() => {
                alert.style.animation = 'slideOutUp 0.3s ease-in';
                setTimeout(() => alert.remove(), 300);
            }, 5000);
        }

        initLucide();
    }

    // ===== Utility =====
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
})();