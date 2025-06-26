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

            // Load album ribbon
            await this.loadAlbumRibbon();

            // Update last update time
            if (overviewData.last_update) {
                this.lastUpdate = new Date(overviewData.last_update);
            } else {
                this.lastUpdate = new Date();
            }

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
            // ✅ FIXED: Display the actual time string, not timeAgo
            nextUpdate.textContent = data.harmoniq_flow.next_update || 'Unknown';
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
            // ✅ FIXED: Display the actual next run string, not timeAgo
            nextRun.textContent = data.library_grower.next_run || 'Unknown';
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
            // ✅ FIXED: Use the new status field
            const statusText = data.system.status || 'Unknown';
            systemStatus.textContent = statusText.charAt(0).toUpperCase() + statusText.slice(1);
            systemStatus.className = `card-status ${data.system.status === 'healthy' ? 'enabled' : 'disabled'}`;
        }

        if (uptime) {
            uptime.textContent = data.system.uptime || 'Unknown';
        }

        if (servicesStatus) {
            // ✅ FIXED: Use the new connected_count/total_count fields
            const connectedCount = data.system.connected_count || 0;
            const totalCount = data.system.total_count || 3;
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

    async loadAlbumRibbon() {
        try {
            const [albumsData, statsData] = await Promise.all([
                window.api.get('/dashboard/recently-added-albums?limit=15'),
                window.api.get('/dashboard/album-stats')
            ]);

            this.updateAlbumRibbon(albumsData);
            this.updateAlbumStats(statsData);

        } catch (error) {
            console.error('Failed to load album ribbon:', error);
            this.showAlbumRibbonError();
        }
    }

    updateAlbumRibbon(albums) {
        const ribbonContainer = document.getElementById('albumRibbon');
        if (!ribbonContainer) return;

        if (!albums || albums.length === 0) {
            ribbonContainer.innerHTML = `
                <div class="album-empty">
                    <i class="fas fa-compact-disc"></i>
                    <h3>No Albums Yet</h3>
                    <p>Albums added by Library Grower will appear here</p>
                </div>
            `;
            return;
        }

        const albumsHTML = albums.map(album => `
            <div class="album-item" onclick="openAlbumDetails('${album.lidarr_id || ''}', '${album.mbid || ''}')">
                <div class="album-cover-container">
                    <img 
                        class="album-cover loading" 
                        src="${album.cover_art_url}" 
                        alt="${album.title} by ${album.artist}"
                        onload="this.classList.remove('loading')"
                        onerror="this.classList.add('error'); this.innerHTML='<i class=\"fas fa-music\"></i>'"
                    />
                </div>
                <div class="album-info">
                    <div class="album-title" title="${album.title}">${album.title}</div>
                    <div class="album-artist" title="${album.artist}">${album.artist}</div>
                    <div class="album-time">${album.relative_time}</div>
                </div>
            </div>
        `).join('');

        ribbonContainer.innerHTML = albumsHTML;

        // Update scroll button states
        this.updateScrollButtons();
    }

    updateAlbumStats(stats) {
        const elements = {
            albumsAddedToday: stats.albums_added_today || 0,
            totalAlbumsAdded: stats.total_albums_added || 0,
            lastAlbumAdded: stats.last_album_added ? 
                window.utils.timeAgo(stats.last_album_added) : 'Never'
        };

        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                if (typeof value === 'number') {
                    this.animateNumber(element, parseInt(element.textContent) || 0, value);
                } else {
                    element.textContent = value;
                }
            }
        });
    }

    showAlbumRibbonError() {
        const ribbonContainer = document.getElementById('albumRibbon');
        if (ribbonContainer) {
            ribbonContainer.innerHTML = `
                <div class="album-empty">
                    <i class="fas fa-exclamation-triangle" style="color: var(--error);"></i>
                    <h3>Failed to Load Albums</h3>
                    <p>Unable to fetch recently added albums</p>
                    <button class="btn btn-primary btn-sm" onclick="dashboard.loadAlbumRibbon()">
                        <i class="fas fa-retry"></i> Retry
                    </button>
                </div>
            `;
        }
    }

    updateScrollButtons() {
        const ribbon = document.getElementById('albumRibbon');
        const leftBtn = document.getElementById('scrollLeft');
        const rightBtn = document.getElementById('scrollRight');

        if (!ribbon || !leftBtn || !rightBtn) return;

        // Check if scrolling is needed
        const needsScroll = ribbon.scrollWidth > ribbon.clientWidth;

        if (!needsScroll) {
            leftBtn.style.display = 'none';
            rightBtn.style.display = 'none';
            return;
        }

        leftBtn.style.display = 'flex';
        rightBtn.style.display = 'flex';

        // Update button states based on scroll position
        leftBtn.disabled = ribbon.scrollLeft <= 0;
        rightBtn.disabled = ribbon.scrollLeft >= (ribbon.scrollWidth - ribbon.clientWidth);
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

window.scrollAlbumRibbon = function(direction) {
    const ribbon = document.getElementById('albumRibbon');
    if (!ribbon) return;

    const scrollAmount = 240; // 2 albums worth
    const currentScroll = ribbon.scrollLeft;

    if (direction === 'left') {
        ribbon.scrollTo({
            left: currentScroll - scrollAmount,
            behavior: 'smooth'
        });
    } else {
        ribbon.scrollTo({
            left: currentScroll + scrollAmount,
            behavior: 'smooth'
        });
    }

    // Update button states after scroll
    setTimeout(() => dashboard.updateScrollButtons(), 300);
};

window.refreshAlbumRibbon = function() {
    window.showToast('Refreshing albums...', 'info', 2000);
    dashboard.loadAlbumRibbon().then(() => {
        window.showToast('Albums updated!', 'success', 2000);
    });
};

window.openAlbumDetails = function(lidarrId, mbid) {
    // TODO: Open album details modal or navigate to Lidarr/Plex
    if (lidarrId) {
        // Open in Lidarr
        window.open(`${config.LIDARR_URL}/album/${lidarrId}`, '_blank');
    } else if (mbid) {
        // Open in MusicBrainz
        window.open(`https://musicbrainz.org/release/${mbid}`, '_blank');
    } else {
        window.showToast('Album details not available', 'info');
    }
};

// Add scroll event listener for button updates
document.addEventListener('DOMContentLoaded', () => {
    const ribbon = document.getElementById('albumRibbon');
    if (ribbon) {
        ribbon.addEventListener('scroll', () => {
            if (dashboard) {
                dashboard.updateScrollButtons();
            }
        });
    }
});

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