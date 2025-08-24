// Advanced Form Manager with Validation and Animations

class FormManager {
    constructor() {
        this.forms = new Map();
        this.validators = new Map();
        this.init();
    }

    init() {
        this.setupFormValidation();
        this.setupAutoSave();
        this.setupFormAnimations();
        this.setupSmartInputs();
    }

    // Register a form with validation rules
    registerForm(formId, options = {}) {
        const form = document.getElementById(formId);
        if (!form) return;

        const defaultOptions = {
            autoSave: true,
            validateOnBlur: true,
            validateOnSubmit: true,
            showSuccessMessage: true,
            showErrorMessage: true,
            animationDuration: 300
        };

        const config = { ...defaultOptions, ...options };
        
        this.forms.set(formId, {
            element: form,
            config: config,
            isValid: false,
            isDirty: false,
            originalData: this.getFormData(form)
        });

        this.setupFormListeners(formId);
    }

    // Setup form validation
    setupFormValidation() {
        // Common validation rules
        this.validators.set('required', (value) => {
            return value && value.trim().length > 0 ? null : 'שדה זה הוא חובה';
        });

        this.validators.set('email', (value) => {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(value) ? null : 'כתובת אימייל לא תקינה';
        });

        this.validators.set('phone', (value) => {
            const phoneRegex = /^[\d\s\-\+\(\)]+$/;
            return phoneRegex.test(value) ? null : 'מספר טלפון לא תקין';
        });

        this.validators.set('number', (value) => {
            return !isNaN(value) && value !== '' ? null : 'ערך זה חייב להיות מספר';
        });

        this.validators.set('minLength', (value, min) => {
            return value.length >= min ? null : `מינימום ${min} תווים נדרשים`;
        });

        this.validators.set('maxLength', (value, max) => {
            return value.length <= max ? null : `מקסימום ${max} תווים מותרים`;
        });

        this.validators.set('positiveNumber', (value) => {
            const num = parseFloat(value);
            return num > 0 ? null : 'הערך חייב להיות חיובי';
        });

        this.validators.set('date', (value) => {
            const date = new Date(value);
            return !isNaN(date.getTime()) ? null : 'תאריך לא תקין';
        });

        this.validators.set('futureDate', (value) => {
            const date = new Date(value);
            const today = new Date();
            return date > today ? null : 'התאריך חייב להיות בעתיד';
        });

        this.validators.set('pastDate', (value) => {
            const date = new Date(value);
            const today = new Date();
            return date < today ? null : 'התאריך חייב להיות בעבר';
        });
    }

    // Setup form listeners
    setupFormListeners(formId) {
        const formData = this.forms.get(formId);
        if (!formData) return;

        const form = formData.element;
        const config = formData.config;

        // Input change listeners
        form.querySelectorAll('input, select, textarea').forEach(input => {
            input.addEventListener('input', () => {
                this.markFormDirty(formId);
                if (config.validateOnBlur) {
                    this.validateField(input);
                }
            });

            input.addEventListener('blur', () => {
                if (config.validateOnBlur) {
                    this.validateField(input);
                }
            });

            input.addEventListener('focus', () => {
                this.clearFieldError(input);
            });
        });

        // Form submit listener
        form.addEventListener('submit', (e) => {
            if (config.validateOnSubmit) {
                const isValid = this.validateForm(formId);
                if (!isValid) {
                    e.preventDefault();
                    this.showFormError(formId, 'יש לתקן שגיאות בטופס');
                }
            }
        });
    }

    // Validate a single field
    validateField(field) {
        const rules = this.getFieldRules(field);
        if (!rules) return true;

        const value = field.value;
        let isValid = true;
        let errorMessage = '';

        for (const [rule, params] of Object.entries(rules)) {
            const validator = this.validators.get(rule);
            if (validator) {
                const result = validator(value, params);
                if (result) {
                    isValid = false;
                    errorMessage = result;
                    break;
                }
            }
        }

        if (isValid) {
            this.clearFieldError(field);
        } else {
            this.showFieldError(field, errorMessage);
        }

        return isValid;
    }

    // Validate entire form
    validateForm(formId) {
        const formData = this.forms.get(formId);
        if (!formData) return false;

        const form = formData.element;
        const fields = form.querySelectorAll('input, select, textarea');
        let isValid = true;

        fields.forEach(field => {
            if (!this.validateField(field)) {
                isValid = false;
            }
        });

        formData.isValid = isValid;
        return isValid;
    }

    // Get field validation rules
    getFieldRules(field) {
        const rules = {};
        
        // Check for data attributes
        if (field.dataset.required) rules.required = true;
        if (field.dataset.email) rules.email = true;
        if (field.dataset.phone) rules.phone = true;
        if (field.dataset.number) rules.number = true;
        if (field.dataset.positiveNumber) rules.positiveNumber = true;
        if (field.dataset.date) rules.date = true;
        if (field.dataset.futureDate) rules.futureDate = true;
        if (field.dataset.pastDate) rules.pastDate = true;
        
        if (field.dataset.minLength) rules.minLength = parseInt(field.dataset.minLength);
        if (field.dataset.maxLength) rules.maxLength = parseInt(field.dataset.maxLength);

        // Check for required attribute
        if (field.hasAttribute('required')) rules.required = true;

        // Check for type attribute
        if (field.type === 'email') rules.email = true;
        if (field.type === 'number') rules.number = true;
        if (field.type === 'date') rules.date = true;

        return Object.keys(rules).length > 0 ? rules : null;
    }

    // Show field error
    showFieldError(field, message) {
        this.clearFieldError(field);
        
        field.classList.add('error');
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'field-error animate-slide-in-right';
        errorDiv.innerHTML = `
            <i class="fas fa-exclamation-circle mr-2"></i>
            ${message}
        `;
        
        field.parentNode.appendChild(errorDiv);
        
        // Add shake animation
        field.style.animation = 'shake 0.5s ease-in-out';
        setTimeout(() => {
            field.style.animation = '';
        }, 500);
    }

    // Clear field error
    clearFieldError(field) {
        field.classList.remove('error');
        const errorDiv = field.parentNode.querySelector('.field-error');
        if (errorDiv) {
            errorDiv.remove();
        }
    }

    // Show form error
    showFormError(formId, message) {
        const formData = this.forms.get(formId);
        if (!formData) return;

        const form = formData.element;
        let errorDiv = form.querySelector('.form-error');
        
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'form-error';
            form.insertBefore(errorDiv, form.firstChild);
        }
        
        errorDiv.innerHTML = `
            <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded animate-fade-in">
                <i class="fas fa-exclamation-triangle mr-2"></i>
                ${message}
            </div>
        `;
    }

    // Clear form error
    clearFormError(formId) {
        const formData = this.forms.get(formId);
        if (!formData) return;

        const form = formData.element;
        const errorDiv = form.querySelector('.form-error');
        if (errorDiv) {
            errorDiv.remove();
        }
    }

    // Mark form as dirty
    markFormDirty(formId) {
        const formData = this.forms.get(formId);
        if (formData) {
            formData.isDirty = true;
        }
    }

    // Get form data
    getFormData(form) {
        const formData = new FormData(form);
        const data = {};
        
        for (const [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        return data;
    }

    // Auto-save functionality
    setupAutoSave() {
        setInterval(() => {
            this.forms.forEach((formData, formId) => {
                if (formData.config.autoSave && formData.isDirty) {
                    this.autoSaveForm(formId);
                }
            });
        }, 30000); // Auto-save every 30 seconds
    }

    // Auto-save form
    autoSaveForm(formId) {
        const formData = this.forms.get(formId);
        if (!formData) return;

        const form = formData.element;
        const data = this.getFormData(form);
        
        // Save to localStorage
        localStorage.setItem(`form_${formId}_autosave`, JSON.stringify({
            data: data,
            timestamp: Date.now()
        }));

        // Show auto-save indicator
        this.showAutoSaveIndicator(formId);
    }

    // Show auto-save indicator
    showAutoSaveIndicator(formId) {
        const formData = this.forms.get(formId);
        if (!formData) return;

        const form = formData.element;
        let indicator = form.querySelector('.autosave-indicator');
        
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.className = 'autosave-indicator fixed bottom-4 right-4 bg-green-500 text-white px-4 py-2 rounded-lg shadow-lg z-50';
            document.body.appendChild(indicator);
        }
        
        indicator.innerHTML = `
            <i class="fas fa-save mr-2"></i>
            נשמר אוטומטית
        `;
        
        indicator.style.animation = 'slideInUp 0.3s ease-out';
        
        setTimeout(() => {
            indicator.style.animation = 'slideOutDown 0.3s ease-out';
            setTimeout(() => {
                indicator.remove();
            }, 300);
        }, 2000);
    }

    // Restore auto-saved data
    restoreAutoSavedData(formId) {
        const saved = localStorage.getItem(`form_${formId}_autosave`);
        if (!saved) return false;

        try {
            const data = JSON.parse(saved);
            const formData = this.forms.get(formId);
            if (!formData) return false;

            const form = formData.element;
            
            // Check if data is not too old (24 hours)
            if (Date.now() - data.timestamp > 24 * 60 * 60 * 1000) {
                localStorage.removeItem(`form_${formId}_autosave`);
                return false;
            }

            // Restore form data
            Object.entries(data.data).forEach(([key, value]) => {
                const field = form.querySelector(`[name="${key}"]`);
                if (field) {
                    field.value = value;
                }
            });

            return true;
        } catch (error) {
            console.error('Error restoring auto-saved data:', error);
            return false;
        }
    }

    // Setup form animations
    setupFormAnimations() {
        // Add CSS animations
        const style = document.createElement('style');
        style.textContent = `
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }

            @keyframes slideInUp {
                from {
                    transform: translateY(100%);
                    opacity: 0;
                }
                to {
                    transform: translateY(0);
                    opacity: 1;
                }
            }

            @keyframes slideOutDown {
                from {
                    transform: translateY(0);
                    opacity: 1;
                }
                to {
                    transform: translateY(100%);
                    opacity: 0;
                }
            }

            .field-error {
                color: #dc2626;
                font-size: 0.875rem;
                margin-top: 0.25rem;
                display: flex;
                align-items: center;
            }

            .form-input.error,
            .form-select.error,
            textarea.error {
                border-color: #dc2626;
                box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1);
            }

            .form-input:focus.error,
            .form-select:focus.error,
            textarea:focus.error {
                border-color: #dc2626;
                box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.2);
            }
        `;
        document.head.appendChild(style);
    }

    // Setup smart inputs
    setupSmartInputs() {
        // Auto-format phone numbers
        document.addEventListener('input', (e) => {
            if (e.target.dataset.phone) {
                this.formatPhoneNumber(e.target);
            }
        });

        // Auto-format currency
        document.addEventListener('input', (e) => {
            if (e.target.dataset.currency) {
                this.formatCurrency(e.target);
            }
        });

        // Auto-complete suggestions
        document.addEventListener('input', (e) => {
            if (e.target.dataset.autocomplete) {
                this.showAutoComplete(e.target);
            }
        });
    }

    // Format phone number
    formatPhoneNumber(input) {
        let value = input.value.replace(/\D/g, '');
        
        if (value.length >= 10) {
            value = value.replace(/(\d{3})(\d{3})(\d{4})/, '($1) $2-$3');
        } else if (value.length >= 6) {
            value = value.replace(/(\d{3})(\d{3})/, '($1) $2-');
        } else if (value.length >= 3) {
            value = value.replace(/(\d{3})/, '($1) ');
        }
        
        input.value = value;
    }

    // Format currency
    formatCurrency(input) {
        let value = input.value.replace(/[^\d.]/g, '');
        
        if (value) {
            const number = parseFloat(value);
            if (!isNaN(number)) {
                input.value = number.toLocaleString('he-IL', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                });
            }
        }
    }

    // Show auto-complete suggestions
    showAutoComplete(input) {
        const suggestions = this.getAutoCompleteSuggestions(input);
        if (suggestions.length === 0) return;

        let dropdown = input.parentNode.querySelector('.autocomplete-dropdown');
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.className = 'autocomplete-dropdown absolute top-full left-0 right-0 bg-white border border-gray-300 rounded-md shadow-lg z-50 max-h-48 overflow-y-auto';
            input.parentNode.style.position = 'relative';
            input.parentNode.appendChild(dropdown);
        }

        dropdown.innerHTML = suggestions.map(suggestion => `
            <div class="px-3 py-2 hover:bg-gray-100 cursor-pointer" onclick="selectSuggestion('${input.id}', '${suggestion}')">
                ${suggestion}
            </div>
        `).join('');

        dropdown.style.display = 'block';
    }

    // Get auto-complete suggestions
    getAutoCompleteSuggestions(input) {
        // This would typically come from a database or API
        const commonSuggestions = {
            'category': ['אוכל', 'בילויים', 'עבודה', 'בית', 'תחבורה', 'בריאות', 'חינוך'],
            'tags': ['חשוב', 'דחוף', 'חודשי', 'שנתי', 'בילוי', 'עבודה', 'בית']
        };

        const fieldType = input.dataset.autocomplete;
        return commonSuggestions[fieldType] || [];
    }

    // Submit form with enhanced functionality
    async submitForm(formId, options = {}) {
        const formData = this.forms.get(formId);
        if (!formData) return false;

        const form = formData.element;
        const config = formData.config;

        // Validate form
        if (config.validateOnSubmit && !this.validateForm(formId)) {
            this.showFormError(formId, 'יש לתקן שגיאות בטופס');
            return false;
        }

        // Show loading state
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn ? submitBtn.innerHTML : '';
        
        if (submitBtn) {
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>שולח...';
            submitBtn.disabled = true;
        }

        try {
            const data = this.getFormData(form);
            
            // Clear auto-saved data on successful submit
            localStorage.removeItem(`form_${formId}_autosave`);
            
            // Show success message
            if (config.showSuccessMessage) {
                showToast('הטופס נשלח בהצלחה!', 'success');
            }

            return true;
        } catch (error) {
            console.error('Form submission error:', error);
            
            if (config.showErrorMessage) {
                this.showFormError(formId, 'שגיאה בשליחת הטופס');
            }
            
            return false;
        } finally {
            // Restore button state
            if (submitBtn) {
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            }
        }
    }
}

// Global form manager instance
const formManager = new FormManager();

// Global functions for easy access
window.selectSuggestion = function(inputId, suggestion) {
    const input = document.getElementById(inputId);
    if (input) {
        input.value = suggestion;
        const dropdown = input.parentNode.querySelector('.autocomplete-dropdown');
        if (dropdown) {
            dropdown.style.display = 'none';
        }
    }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FormManager;
}
