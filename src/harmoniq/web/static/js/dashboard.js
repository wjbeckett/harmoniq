/**
 * Dashboard JavaScript for Harmoniq Web UI
 * Handles real-time updates, service status, and user interactions
 */

class HarmoniqDashboard {
    constructor() {
        this.refreshInterval = null;
        this.refreshRate = 30000; // 30 seconds
        this.isRefreshing = false;
        this.lastUpdate = null;

        this.init();
    }

    async init() {
        console.log('🎵 Initializing Harmoniq Dashboard...');

        // Initial data load
        await this.loadDashboardData();

        // Start auto-refresh
        this.startAutoRefresh();

        // Setup event listeners
        this.setupEventListeners();

        console.log('✅ Dashboard initialized successfully!');
    }

    setupEventListeners() {
        // Refresh button
        const refreshBtn = document.querySelector('[onclick="refreshDashboard()"]');
        if (refreshBtn) {
            refreshBtn.onclick = () => this.refreshDashboard();
        }

        // Service test buttons are handled by onclick attributes in HTML

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + R for refresh
            if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
                e.preventDefault();
                this.refreshDashboard();
            }
        });

        // Visibility change - pause/resume refresh when tab is hidden/visible
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopAutoRefresh();
            } else {
                this.startAutoRefresh();
                this.refreshDashboard(); // Refresh when coming back
            }
        });
    }

    async loadDashboardData() {
        try {
            this.isRefreshing = true;
            this.updateRefreshButton(true);

            // Load all dashboard data concurrently
            const [overviewData, serviceStatus, recentActivity, stats] = await Promise.all([
                window.api.get('/dashboard/overview'),
                window.api.get('/status/services'),
                window.api.get('/dashboard/recent-activity'),
                window.api.get('/dashboard/stats')
            ]);

            // Update UI with loaded data
            this.updateOverviewCards(overviewData);
            this.updateServiceStatus(serviceStatus);
            this.updateRecentActivity(recentActivity);
            this.updateStats(stats);

            this.lastUpdate = new Date();

        } catch (error) {
            console.error('Failed to load dashboard data:', error);
            window.showToast('Failed to load dashboard data', 'error');
        } finally {
            this.isRefreshing = false;
            this.updateRefreshButton(false);
        }
    }

    updateOverviewCards(data) {
        // Harmoniq Flow Card
        const flowStatus = document.getElementById('flowStatus');
        const activePeriod = document.getElementById('activePeriod');
        const nextUpdate = document.getElementById('nextUpdate');
        const totalPeriods = document.getElementById('totalPeriods');

        if (flowStatus) {
            flowStatus.textContent = data.harmoniq_flow.enabled ? 'Enabled' : 'Disabled';
            flowStatus.className = `card-status ${data.harmoniq_flow.enabled ? 'enabled' : 'disabled'}`;
        }

        if (activePeriod) {
            activePeriod.textContent = data.harmoniq_flow.active_period || 'None';
        }

        if (nextUpdate) {
            nextUpdate.textContent = data.harmoniq_flow.next_update 
                ? window.utils.timeAgo(data.harmoniq_flow.next_update)
                : 'Unknown';
        }

        if (totalPeriods) {
            totalPeriods.textContent = data.harmoniq_flow.total_periods || '0';
        }

        // Library Grower Card
        const growerStatus = document.getElementById('growerStatus');
        const nextRun = document.getElementById('nextRun');
        const albumsToday = document.getElementById('albumsToday');
        const totalAlbums = document.getElementById('totalAlbums');

        if (growerStatus) {
            growerStatus.textContent = data.library_grower.enabled ? 'Enabled' : 'Disabled';
            growerStatus.className = `card-status ${data.library_grower.enabled ? 'enabled' : 'disabled'}`;
        }

        if (nextRun) {
            nextRun.textContent = data.library_grower.next_run 
                ? window.utils.timeAgo(data.library_grower.next_run)
                : 'Unknown';
        }

        if (albumsToday) {
            albumsToday.textContent = data.library_grower.albums_added_today || '0';
        }

        if (totalAlbums) {
            totalAlbums.textContent = data.library_grower.total_albums_added || '0';
        }

        // System Status Card
        const systemStatus = document.getElementById('systemStatus');
        const uptime = document.getElementById('uptime');
        const servicesStatus = document.getElementById('servicesStatus');
        const lastError = document.getElementById('lastError');

        if (systemStatus) {
            const isHealthy = data.system.services_connected && 
                            Object.values(data.system.services_connected).every(status => 
                                status === null || status === true
                            );
            systemStatus.textContent = isHealthy ? 'Healthy' : 'Issues';
            systemStatus.className = `card-status ${isHealthy ? 'enabled' : 'disabled'}`;
        }

        if (uptime) {
            uptime.textContent = data.system.uptime || 'Unknown';
        }

        if (servicesStatus) {
            const connectedCount = Object.values(data.system.services_connected || {})
                .filter(status => status === true).length;
            const totalCount = Object.keys(data.system.services_connected || {}).length;
            servicesStatus.textContent = `${connectedCount}/${totalCount}`;
        }

        if (lastError) {
            lastError.textContent = data.system.last_error || 'None';
        }
    }

    updateServiceStatus(data) {
        const services = ['plex', 'lastfm', 'lidarr'];

        services.forEach(service => {
            const serviceData = data[service];
            if (!serviceData) return;

            // Update status badge
            const statusEl = document.getElementById(`${service}Status`);
            if (statusEl) {
                statusEl.textContent = this.getStatusText(serviceData.status);
                statusEl.className = `service-status ${serviceData.status}`;
            }

            // Update service details
            this.updateServiceDetails(service, serviceData);
        });
    }

    updateServiceDetails(service, data) {
        if (service === 'plex') {
            const serverEl = document.getElementById('plexServer');
            const versionEl = document.getElementById('plexVersion');

            if (serverEl) serverEl.textContent = data.server_name || 'Unknown';
            if (versionEl) versionEl.textContent = data.version || 'Unknown';

        } else if (service === 'lastfm') {
            const userEl = document.getElementById('lastfmUser');
            const apiEl = document.getElementById('lastfmApi');

            if (userEl) userEl.textContent = data.username || 'Not configured';
            if (apiEl) apiEl.textContent = data.test_result || data.error || 'Unknown';

        } else if (service === 'lidarr') {
            const urlEl = document.getElementById('lidarrUrl');
            const connectionEl = document.getElementById('lidarrConnection');

            if (urlEl) urlEl.textContent = data.url || 'Not configured';
            if (connectionEl) connectionEl.textContent = data.test_result || data.error || 'Unknown';
        }
    }

    updateRecentActivity(activities) {
        const activityFeed = document.getElementById('activityFeed');
        if (!activityFeed) return;

        if (!activities || activities.length === 0) {
            activityFeed.innerHTML = `
                <div class="activity-loading">
                    <i class="fas fa-info-circle" style="color: var(--info);"></i>
                    <span>No recent activity</span>
                </div>
            `;
            return;
        }

        const activityHTML = activities.map(activity => `
            <div class="activity-item fade-in">
                <div class="activity-icon ${activity.status}">
                    <i class="${this.getActivityIcon(activity.type)}"></i>
                </div>
                <div class="activity-content">
                    <div class="activity-message">${activity.message}</div>
                    <div class="activity-time">${window.utils.timeAgo(activity.timestamp)}</div>
                </div>
            </div>
        `).join('');

        activityFeed.innerHTML = activityHTML;
    }

    updateStats(stats) {
        const statElements = {
            playlistsUpdated: stats.total_playlists_updated,
            albumsDiscovered: stats.total_albums_discovered,
            artistsProcessed: stats.total_artists_processed,
            uptimeDays: stats.uptime_days
        };

        Object.entries(statElements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                // Animate number change
                this.animateNumber(element, parseInt(element.textContent) || 0, value || 0);
            }
        });
    }

    animateNumber(element, from, to, duration = 1000) {
        const startTime = performance.now();
        const difference = to - from;

        const updateNumber = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Easing function
            const easeOutQuart = 1 - Math.pow(1 - progress, 4);
            const current = Math.round(from + (difference * easeOutQuart));

            element.textContent = current.toLocaleString();

            if (progress < 1) {
                requestAnimationFrame(updateNumber);
            }
        };

        requestAnimationFrame(updateNumber);
    }

    getStatusText(status) {
        const statusMap = {
            connected: 'Connected',
            disconnected: 'Disconnected',
            disabled: 'Disabled',
            not_configured: 'Not Configured',
            checking: 'Checking...',
            error: 'Error'
        };

        return statusMap[status] || status;
    }

    getActivityIcon(type) {
        const iconMap = {
            library_grower: 'fas fa-seedling',
            harmoniq_flow: 'fas fa-stream',
            system: 'fas fa-server',
            plex: 'fas fa-play',
            lastfm: 'fas fa-music',
            lidarr: 'fas fa-download'
        };

        return iconMap[type] || 'fas fa-info-circle';
    }

    updateRefreshButton(isRefreshing) {
        const refreshBtn = document.querySelector('[onclick="refreshDashboard()"]');
        if (refreshBtn) {
            const icon = refreshBtn.querySelector('i');
            if (icon) {
                icon.className = isRefreshing ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt';
            }
            refreshBtn.disabled = isRefreshing;
        }
    }

    async refreshDashboard() {
        if (this.isRefreshing) return;

        window.showToast('Refreshing dashboard...', 'info', 2000);
        await this.loadDashboardData();
        window.showToast('Dashboard updated!', 'success', 2000);
    }

    startAutoRefresh() {
        this.stopAutoRefresh(); // Clear any existing interval
        this.refreshInterval = setInterval(() => {
            this.loadDashboardData();
        }, this.refreshRate);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    destroy() {
        this.stopAutoRefresh();
        // Remove event listeners if needed
    }
}

// Service connection testing
async function testService(serviceName) {
    const button = event.target.closest('.test-btn');
    const originalText = button.innerHTML;

    try {
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
        button.disabled = true;

        const result = await window.api.post(`/status/test-connection/${serviceName}`);

        // Update the service status immediately
        const statusEl = document.getElementById(`${serviceName}Status`);
        if (statusEl) {
            statusEl.textContent = dashboard.getStatusText(result.status);
            statusEl.className = `service-status ${result.status}`;
        }

        // Update service details
        dashboard.updateServiceDetails(serviceName, result);

        // Show result toast
        const isSuccess = result.status === 'connected';
        window.showToast(
            `${serviceName.charAt(0).toUpperCase() + serviceName.slice(1)} test: ${result.status}`,
            isSuccess ? 'success' : 'error'
        );

    } catch (error) {
        console.error(`Service test failed for ${serviceName}:`, error);
        window.showToast(`Failed to test ${serviceName} connection`, 'error');
    } finally {
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

// Global functions
window.refreshDashboard = () => dashboard.refreshDashboard();
window.testService = testService;

// Initialize dashboard when DOM is ready
let dashboard;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        dashboard = new HarmoniqDashboard();
        window.dashboard = dashboard;
    });
} else {
    dashboard = new HarmoniqDashboard();
    window.dashboard = dashboard;
}

console.log('🎵 Dashboard JavaScript loaded!');