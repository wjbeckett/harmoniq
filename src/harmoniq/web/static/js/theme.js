/**
 * Theme Management for Harmoniq Web UI
 * Handles light/dark/auto theme switching with smooth transitions
 */

class ThemeManager {
    constructor() {
        this.themes = ['light', 'dark', 'auto'];
        this.currentTheme = this.getStoredTheme() || 'auto';
        this.init();
    }

    init() {
        this.applyTheme(this.currentTheme);
        this.setupEventListeners();
        this.updateThemeToggle();

        // Listen for system theme changes when in auto mode
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
                if (this.currentTheme === 'auto') {
                    this.applyTheme('auto');
                }
            });
        }
    }

    setupEventListeners() {
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => this.cycleTheme());
        }

        // Keyboard shortcut: Ctrl/Cmd + Shift + T
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'T') {
                e.preventDefault();
                this.cycleTheme();
            }
        });
    }

    cycleTheme() {
        const currentIndex = this.themes.indexOf(this.currentTheme);
        const nextIndex = (currentIndex + 1) % this.themes.length;
        const nextTheme = this.themes[nextIndex];

        this.setTheme(nextTheme);
    }

    setTheme(theme) {
        if (!this.themes.includes(theme)) {
            console.warn(`Invalid theme: ${theme}`);
            return;
        }

        this.currentTheme = theme;
        this.applyTheme(theme);
        this.storeTheme(theme);
        this.updateThemeToggle();
        this.showThemeToast(theme);
    }

    applyTheme(theme) {
        const html = document.documentElement;

        // Add transition class for smooth theme switching
        html.classList.add('theme-transitioning');

        // Apply theme
        html.setAttribute('data-theme', theme);

        // Remove transition class after animation
        setTimeout(() => {
            html.classList.remove('theme-transitioning');
        }, 300);
    }

    updateThemeToggle() {
        const icons = document.querySelectorAll('.theme-icon');
        icons.forEach(icon => icon.classList.remove('active'));

        const activeIcon = document.querySelector(`.${this.currentTheme}-icon`);
        if (activeIcon) {
            activeIcon.classList.add('active');
        }
    }

    getStoredTheme() {
        try {
            return localStorage.getItem('harmoniq-theme');
        } catch (e) {
            console.warn('Could not access localStorage for theme');
            return null;
        }
    }

    storeTheme(theme) {
        try {
            localStorage.setItem('harmoniq-theme', theme);
        } catch (e) {
            console.warn('Could not store theme in localStorage');
        }
    }

    showThemeToast(theme) {
        const themeNames = {
            light: 'Light Theme',
            dark: 'Dark Theme',
            auto: 'Auto Theme (System)'
        };

        const message = `Switched to ${themeNames[theme]}`;

        // Use the toast system if available
        if (window.showToast) {
            window.showToast(message, 'info', 2000);
        } else {
            console.log(message);
        }
    }

    getCurrentTheme() {
        return this.currentTheme;
    }

    getEffectiveTheme() {
        if (this.currentTheme === 'auto') {
            return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches 
                ? 'dark' 
                : 'light';
        }
        return this.currentTheme;
    }
}

// Add smooth theme transition CSS
const themeTransitionCSS = `
    html.theme-transitioning,
    html.theme-transitioning *,
    html.theme-transitioning *:before,
    html.theme-transitioning *:after {
        transition: all 0.3s ease !important;
        transition-delay: 0 !important;
    }
`;

// Inject transition CSS
const style = document.createElement('style');
style.textContent = themeTransitionCSS;
document.head.appendChild(style);

// Initialize theme manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
    });
} else {
    window.themeManager = new ThemeManager();
}

// Export for use in other scripts
window.ThemeManager = ThemeManager;