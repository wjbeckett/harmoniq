/**
 * Utility Functions for Harmoniq Web UI
 * Common functions for API calls, notifications, loading states, etc.
 */

// Toast Notification System
class ToastManager {
    constructor() {
        this.container = document.getElementById('toastContainer');
        this.toasts = new Map();
        this.toastId = 0;
    }

    show(message, type = 'info', duration = 5000) {
        const id = ++this.toastId;
        const toast = this.createToast(id, message, type);

        this.container.appendChild(toast);
        this.toasts.set(id, toast);

        // Trigger show animation
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => this.remove(id), duration);
        }

        return id;
    }

    createToast(id, message, type) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.dataset.toastId = id;

        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };

        toast.innerHTML = `
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <i class="${icons[type] || icons.info}" style="color: var(--${type}); font-size: 1.125rem;"></i>
                <span style="flex: 1; color: var(--text-primary);">${message}</span>
                <button onclick="window.toastManager.remove(${id})" 
                        style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 0.25rem;">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

        return toast;
    }

    remove(id) {
        const toast = this.toasts.get(id);
        if (toast) {
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
                this.toasts.delete(id);
            }, 300);
        }
    }

    clear() {
        this.toasts.forEach((toast, id) => this.remove(id));
    }
}

// Loading Overlay Manager
class LoadingManager {
    constructor() {
        this.overlay = document.getElementById('loadingOverlay');
        this.isVisible = false;
    }

    show(message = 'Loading...') {
        if (this.overlay) {
            const messageEl = this.overlay.querySelector('p');
            if (messageEl) {
                messageEl.textContent = message;
            }
            this.overlay.classList.add('active');
            this.isVisible = true;
        }
    }

    hide() {
        if (this.overlay) {
            this.overlay.classList.remove('active');
            this.isVisible = false;
        }
    }

    toggle(show, message) {
        if (show) {
            this.show(message);
        } else {
            this.hide();
        }
    }
}

// API Client
class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.defaultHeaders = {
            'Content-Type': 'application/json',
        };
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options
        };

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            } else {
                return await response.text();
            }
        } catch (error) {
            console.error(`API request failed: ${url}`, error);
            throw error;
        }
    }

    async get(endpoint, params = {}) {
        const url = new URL(endpoint, window.location.origin);
        Object.keys(params).forEach(key => {
            if (params[key] !== undefined && params[key] !== null) {
                url.searchParams.append(key, params[key]);
            }
        });

        return this.request(url.pathname + url.search);
    }

    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async delete(endpoint) {
        return this.request(endpoint, {
            method: 'DELETE'
        });
    }
}

// Utility Functions
const utils = {
    // Format time ago
    timeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffInSeconds = Math.floor((now - date) / 1000);

        const intervals = [
            { label: 'year', seconds: 31536000 },
            { label: 'month', seconds: 2592000 },
            { label: 'day', seconds: 86400 },
            { label: 'hour', seconds: 3600 },
            { label: 'minute', seconds: 60 },
            { label: 'second', seconds: 1 }
        ];

        for (const interval of intervals) {
            const count = Math.floor(diffInSeconds / interval.seconds);
            if (count >= 1) {
                return `${count} ${interval.label}${count > 1 ? 's' : ''} ago`;
            }
        }

        return 'just now';
    },

    // Format duration
    formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    },

    // Debounce function
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Throttle function
    throttle(func, limit) {
        let inThrottle;
        return function() {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    // Copy to clipboard
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            window.showToast('Copied to clipboard!', 'success', 2000);
            return true;
        } catch (err) {
            console.error('Failed to copy to clipboard:', err);
            window.showToast('Failed to copy to clipboard', 'error');
            return false;
        }
    },

    // Format file size
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    // Validate email
    isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    },

    // Validate URL
    isValidUrl(string) {
        try {
            new URL(string);
            return true;
        } catch (_) {
            return false;
        }
    },

    // Generate random ID
    generateId(length = 8) {
        const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        let result = '';
        for (let i = 0; i < length; i++) {
            result += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        return result;
    },

    // Local storage helpers
    storage: {
        get(key, defaultValue = null) {
            try {
                const item = localStorage.getItem(key);
                return item ? JSON.parse(item) : defaultValue;
            } catch (e) {
                console.warn(`Failed to get ${key} from localStorage:`, e);
                return defaultValue;
            }
        },

        set(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
                return true;
            } catch (e) {
                console.warn(`Failed to set ${key} in localStorage:`, e);
                return false;
            }
        },

        remove(key) {
            try {
                localStorage.removeItem(key);
                return true;
            } catch (e) {
                console.warn(`Failed to remove ${key} from localStorage:`, e);
                return false;
            }
        }
    }
};

// Initialize managers
const toastManager = new ToastManager();
const loadingManager = new LoadingManager();
const apiClient = new ApiClient('/api');

// Global functions
window.showToast = (message, type, duration) => toastManager.show(message, type, duration);
window.showLoading = (message) => loadingManager.show(message);
window.hideLoading = () => loadingManager.hide();
window.api = apiClient;
window.utils = utils;

// Export managers
window.toastManager = toastManager;
window.loadingManager = loadingManager;
window.apiClient = apiClient;

console.log('🎵 Harmoniq Web UI utilities loaded successfully!');