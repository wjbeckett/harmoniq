
/**
 * Album Recommendations Page JavaScript
 * Handles all interactions for the recommendations interface
 */

class RecommendationsManager {
    constructor() {
        this.currentFilter = 'pending';
        this.currentSearch = '';
        this.selectedAlbums = new Set();
        this.recommendations = [];
        this.statistics = {};
        this.isLoading = false;
        this.hasMore = true;
        this.currentPage = 0;
        this.pageSize = 20;

        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.loadStatistics();
        await this.loadRecommendations();
        this.updateUI();
    }

    setupEventListeners() {
        // Search input
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            let searchTimeout;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    this.handleSearch(e.target.value);
                }, 300);
            });
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case 'a':
                        e.preventDefault();
                        this.selectAll();
                        break;
                    case 'Enter':
                        e.preventDefault();
                        if (this.selectedAlbums.size > 0) {
                            this.bulkApprove();
                        }
                        break;
                }
            }

            if (e.key === 'Escape') {
                this.clearSelection();
                this.closePreviewModal();
            }
        });

        // Modal click outside to close
        const modal = document.getElementById('albumPreviewModal');
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.closePreviewModal();
                }
            });
        }
    }

    async loadStatistics() {
        try {
            const response = await window.api.get('/recommendations/statistics');
            this.statistics = response;
            this.updateStatistics();
        } catch (error) {
            console.error('Failed to load statistics:', error);
            window.showToast('Failed to load statistics', 'error');
        }
    }

    async loadRecommendations(reset = false) {
        if (this.isLoading) return;

        try {
            this.isLoading = true;
            this.showLoading();

            if (reset) {
                this.currentPage = 0;
                this.recommendations = [];
                this.hasMore = true;
            }

            const params = new URLSearchParams({
                limit: this.pageSize,
                offset: this.currentPage * this.pageSize
            });

            if (this.currentFilter !== 'all') {
                params.append('status', this.currentFilter);
            }

            if (this.currentSearch) {
                params.append('search', this.currentSearch);
            }

            const endpoint = this.currentFilter === 'pending' ? 
                '/recommendations/pending' : '/recommendations/all';

            const newRecommendations = await window.api.get(`${endpoint}?${params}`);

            if (reset) {
                this.recommendations = newRecommendations;
            } else {
                this.recommendations.push(...newRecommendations);
            }

            this.hasMore = newRecommendations.length === this.pageSize;
            this.currentPage++;

            this.renderRecommendations();
            this.updateLoadMoreButton();

        } catch (error) {
            console.error('Failed to load recommendations:', error);
            window.showToast('Failed to load recommendations', 'error');
            this.showError();
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    renderRecommendations() {
        const grid = document.getElementById('recommendationsGrid');
        const emptyState = document.getElementById('emptyState');

        if (!grid) return;

        if (this.recommendations.length === 0) {
            grid.style.display = 'none';
            if (emptyState) emptyState.style.display = 'block';
            return;
        }

        grid.style.display = 'grid';
        if (emptyState) emptyState.style.display = 'none';

        // Clear existing content except loading state
        const loadingState = grid.querySelector('.loading-state');
        grid.innerHTML = '';
        if (loadingState && this.isLoading) {
            grid.appendChild(loadingState);
        }

        this.recommendations.forEach(album => {
            const albumCard = this.createAlbumCard(album);
            grid.appendChild(albumCard);
        });
    }

    createAlbumCard(album) {
        const card = document.createElement('div');
        card.className = `album-card ${this.selectedAlbums.has(album.id) ? 'selected' : ''}`;
        card.dataset.albumId = album.id;

        const statusClass = album.status.toLowerCase();
        const statusText = album.status.charAt(0).toUpperCase() + album.status.slice(1);

        // Generate action buttons based on status
        let actionButtons = '';
        if (album.status === 'pending') {
            actionButtons = `
                <button class="album-action-btn approve" onclick="recommendationsManager.updateAlbumStatus('${album.id}', 'approved')">
                    <i class="fas fa-check"></i>
                    Approve
                </button>
                <button class="album-action-btn deny" onclick="recommendationsManager.updateAlbumStatus('${album.id}', 'denied')">
                    <i class="fas fa-times"></i>
                    Deny
                </button>
                <button class="album-action-btn maybe" onclick="recommendationsManager.updateAlbumStatus('${album.id}', 'maybe')">
                    <i class="fas fa-question"></i>
                    Maybe
                </button>
            `;
        } else {
            actionButtons = `
                <button class="album-action-btn approve" onclick="recommendationsManager.updateAlbumStatus('${album.id}', 'approved')" ${album.status === 'approved' ? 'disabled' : ''}>
                    <i class="fas fa-check"></i>
                    ${album.status === 'approved' ? 'Approved' : 'Approve'}
                </button>
                <button class="album-action-btn deny" onclick="recommendationsManager.updateAlbumStatus('${album.id}', 'denied')" ${album.status === 'denied' ? 'disabled' : ''}>
                    <i class="fas fa-times"></i>
                    ${album.status === 'denied' ? 'Denied' : 'Deny'}
                </button>
            `;
        }

        // Generate tags
        const tags = album.tags ? album.tags.slice(0, 3).map(tag => 
            `<span class="album-tag">${tag}</span>`
        ).join('') : '';

        // Generate rating
        const rating = album.external_ratings && album.external_ratings.lastfm_listeners ? 
            `<div class="album-rating">
                <i class="fas fa-users"></i>
                ${parseInt(album.external_ratings.lastfm_listeners).toLocaleString()} listeners
            </div>` : '';

        card.innerHTML = `
            <div class="album-status ${statusClass}">${statusText}</div>
            <input type="checkbox" class="album-select" ${this.selectedAlbums.has(album.id) ? 'checked' : ''} 
                   onchange="recommendationsManager.toggleSelection('${album.id}')">

            <div class="album-card-header">
                <div class="album-cover-container">
                    <img class="album-cover loading" 
                         src="${album.cover_art_url || '/static/images/album-placeholder.png'}" 
                         alt="${album.title} by ${album.artist}"
                         onload="this.classList.remove('loading')"
                         onerror="this.classList.add('error'); this.innerHTML='<i class=\"fas fa-music\"></i>'">
                </div>
                <div class="album-info">
                    <div class="album-title" title="${album.title}">${album.title}</div>
                    <div class="album-artist" title="${album.artist}">${album.artist}</div>
                    ${album.year ? `<div class="album-year">${album.year}</div>` : ''}
                </div>
            </div>

            <div class="album-metadata">
                ${tags ? `<div class="album-tags">${tags}</div>` : ''}
                ${rating}
                <div class="album-time">${album.relative_time}</div>
            </div>

            <div class="album-actions">
                ${actionButtons}
                <button class="album-action-btn preview" onclick="recommendationsManager.showPreview('${album.id}')" title="Preview">
                    <i class="fas fa-eye"></i>
                </button>
            </div>
        `;

        return card;
    }

    updateStatistics() {
        const elements = {
            'pendingCount': this.statistics.pending || 0,
            'approvedCount': this.statistics.approved || 0,
            'approvalRate': `${this.statistics.approval_rate || 0}%`,
            'totalAdded': this.statistics.total_added || 0
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

        // Update tab counts
        const tabCounts = {
            'pendingTabCount': this.statistics.pending || 0,
            'approvedTabCount': this.statistics.approved || 0,
            'deniedTabCount': this.statistics.denied || 0,
            'allTabCount': (this.statistics.pending || 0) + (this.statistics.approved || 0) + (this.statistics.denied || 0) + (this.statistics.maybe || 0)
        };

        Object.entries(tabCounts).forEach(([id, count]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = count;
            }
        });
    }

    animateNumber(element, from, to) {
        const duration = 1000;
        const start = Date.now();
        const step = () => {
            const progress = Math.min((Date.now() - start) / duration, 1);
            const current = Math.floor(from + (to - from) * progress);
            element.textContent = current;
            if (progress < 1) {
                requestAnimationFrame(step);
            }
        };
        requestAnimationFrame(step);
    }

    async updateAlbumStatus(albumId, status, userNotes = '') {
        try {
            await window.api.post(`/recommendations/update-status/${albumId}`, {
                status: status,
                user_notes: userNotes
            });

            // Update local data
            const album = this.recommendations.find(a => a.id === albumId);
            if (album) {
                album.status = status;
                album.user_notes = userNotes;
            }

            // Re-render the specific card
            const card = document.querySelector(`[data-album-id="${albumId}"]`);
            if (card) {
                const newCard = this.createAlbumCard(album);
                card.replaceWith(newCard);
            }

            // Update statistics
            await this.loadStatistics();

            const statusText = status.charAt(0).toUpperCase() + status.slice(1);
            window.showToast(`Album ${statusText.toLowerCase()}!`, 'success');

        } catch (error) {
            console.error('Failed to update album status:', error);
            window.showToast('Failed to update album status', 'error');
        }
    }

    async bulkApprove() {
        await this.bulkUpdateStatus('approved');
    }

    async bulkDeny() {
        await this.bulkUpdateStatus('denied');
    }

    async bulkUpdateStatus(status) {
        if (this.selectedAlbums.size === 0) {
            window.showToast('No albums selected', 'warning');
            return;
        }

        try {
            const albumIds = Array.from(this.selectedAlbums);
            await window.api.post('/recommendations/bulk-update', {
                album_ids: albumIds,
                status: status
            });

            // Update local data
            albumIds.forEach(albumId => {
                const album = this.recommendations.find(a => a.id === albumId);
                if (album) {
                    album.status = status;
                }
            });

            this.clearSelection();
            this.renderRecommendations();
            await this.loadStatistics();

            const statusText = status.charAt(0).toUpperCase() + status.slice(1);
            window.showToast(`${albumIds.length} albums ${statusText.toLowerCase()}!`, 'success');

        } catch (error) {
            console.error('Failed to bulk update:', error);
            window.showToast('Failed to bulk update albums', 'error');
        }
    }

    toggleSelection(albumId) {
        if (this.selectedAlbums.has(albumId)) {
            this.selectedAlbums.delete(albumId);
        } else {
            this.selectedAlbums.add(albumId);
        }

        this.updateSelectionUI();
    }

    selectAll() {
        const visibleAlbums = this.recommendations.filter(album => 
            this.currentFilter === 'all' || album.status === this.currentFilter
        );

        visibleAlbums.forEach(album => {
            this.selectedAlbums.add(album.id);
        });

        this.updateSelectionUI();
        this.renderRecommendations();
    }

    clearSelection() {
        this.selectedAlbums.clear();
        this.updateSelectionUI();
        this.renderRecommendations();
    }

    updateSelectionUI() {
        const bulkActions = document.getElementById('bulkActions');
        const selectedCount = document.getElementById('selectedCount');

        if (this.selectedAlbums.size > 0) {
            if (bulkActions) bulkActions.style.display = 'flex';
            if (selectedCount) selectedCount.textContent = this.selectedAlbums.size;
        } else {
            if (bulkActions) bulkActions.style.display = 'none';
        }
    }

    async switchFilter(filter) {
        this.currentFilter = filter;

        // Update active tab
        document.querySelectorAll('.filter-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        document.querySelector(`[data-status="${filter}"]`).classList.add('active');

        // Clear selection and reload
        this.clearSelection();
        await this.loadRecommendations(true);
    }

    async handleSearch(query) {
        this.currentSearch = query;

        // Update search clear button
        const clearBtn = document.querySelector('.search-clear');
        if (clearBtn) {
            clearBtn.style.display = query ? 'block' : 'none';
        }

        // Clear selection and reload
        this.clearSelection();
        await this.loadRecommendations(true);
    }

    clearSearch() {
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.value = '';
            this.handleSearch('');
        }
    }

    async loadMoreRecommendations() {
        if (!this.hasMore || this.isLoading) return;
        await this.loadRecommendations(false);
    }

    updateLoadMoreButton() {
        const container = document.getElementById('loadMoreContainer');
        if (container) {
            container.style.display = this.hasMore ? 'block' : 'none';
        }
    }

    async showPreview(albumId) {
        try {
            const album = this.recommendations.find(a => a.id === albumId);
            if (!album) return;

            const previewData = await window.api.get(`/recommendations/preview/${albumId}`);

            const modal = document.getElementById('albumPreviewModal');
            const title = document.getElementById('previewAlbumTitle');
            const body = document.getElementById('previewModalBody');

            if (title) title.textContent = `${album.artist} - ${album.title}`;

            if (body) {
                body.innerHTML = `
                    <div class="preview-content">
                        <img class="preview-cover" src="${album.cover_art_url || '/static/images/album-placeholder.png'}" 
                             alt="${album.title}" onerror="this.src='/static/images/album-placeholder.png'">
                        <div class="preview-info">
                            <h3>${album.title}</h3>
                            <div class="artist">${album.artist}</div>
                            ${album.year ? `<div class="year">${album.year}</div>` : ''}
                            ${album.external_ratings && album.external_ratings.lastfm_listeners ? 
                                `<div class="listeners">${parseInt(album.external_ratings.lastfm_listeners).toLocaleString()} Last.fm listeners</div>` : ''}
                        </div>
                    </div>
                    <div class="preview-links">
                        <a href="${previewData.youtube_search_url}" target="_blank" class="preview-link">
                            <i class="fab fa-youtube"></i>
                            Listen on YouTube
                        </a>
                        <a href="${previewData.spotify_search_url}" target="_blank" class="preview-link">
                            <i class="fab fa-spotify"></i>
                            Find on Spotify
                        </a>
                        <a href="${previewData.lastfm_url}" target="_blank" class="preview-link">
                            <i class="fab fa-lastfm"></i>
                            View on Last.fm
                        </a>
                        ${previewData.musicbrainz_url ? `
                            <a href="${previewData.musicbrainz_url}" target="_blank" class="preview-link">
                                <i class="fas fa-database"></i>
                                MusicBrainz
                            </a>
                        ` : ''}
                    </div>
                `;
            }

            if (modal) modal.style.display = 'flex';

        } catch (error) {
            console.error('Failed to load preview:', error);
            window.showToast('Failed to load album preview', 'error');
        }
    }

    closePreviewModal() {
        const modal = document.getElementById('albumPreviewModal');
        if (modal) modal.style.display = 'none';
    }

    showLoading() {
        const grid = document.getElementById('recommendationsGrid');
        const loadingState = document.getElementById('loadingState');

        if (grid && loadingState) {
            loadingState.style.display = 'flex';
        }
    }

    hideLoading() {
        const loadingState = document.getElementById('loadingState');
        if (loadingState) {
            loadingState.style.display = 'none';
        }
    }

    showError() {
        const grid = document.getElementById('recommendationsGrid');
        if (grid) {
            grid.innerHTML = `
                <div class="loading-state">
                    <i class="fas fa-exclamation-triangle" style="color: var(--error);"></i>
                    <span>Failed to load recommendations</span>
                    <button class="btn btn-primary btn-sm" onclick="recommendationsManager.loadRecommendations(true)">
                        <i class="fas fa-retry"></i> Retry
                    </button>
                </div>
            `;
        }
    }

    updateUI() {
        this.updateSelectionUI();
        this.updateLoadMoreButton();
    }
}

// Global functions
let recommendationsManager;

async function triggerDiscovery() {
    try {
        window.showToast('Starting album discovery...', 'info');

        const response = await window.api.post('/recommendations/discover', {
            force_refresh: true
        });

        window.showToast(`Discovery complete! Found ${response.results.new_recommendations} new recommendations`, 'success');

        // Reload recommendations and statistics
        await recommendationsManager.loadStatistics();
        await recommendationsManager.loadRecommendations(true);

    } catch (error) {
        console.error('Failed to trigger discovery:', error);
        window.showToast('Failed to start discovery', 'error');
    }
}

async function processApproved() {
    try {
        window.showToast('Processing approved albums...', 'info');

        const response = await window.api.post('/recommendations/process-approved');

        if (response.results.successful > 0) {
            window.showToast(`Successfully added ${response.results.successful} albums to Lidarr!`, 'success');
        } else {
            window.showToast('No approved albums to process', 'info');
        }

        // Reload recommendations and statistics
        await recommendationsManager.loadStatistics();
        await recommendationsManager.loadRecommendations(true);

    } catch (error) {
        console.error('Failed to process approved albums:', error);
        window.showToast('Failed to process approved albums', 'error');
    }
}

function switchFilter(filter) {
    recommendationsManager.switchFilter(filter);
}

function clearSearch() {
    recommendationsManager.clearSearch();
}

function bulkApprove() {
    recommendationsManager.bulkApprove();
}

function bulkDeny() {
    recommendationsManager.bulkDeny();
}

function clearSelection() {
    recommendationsManager.clearSelection();
}

function loadMoreRecommendations() {
    recommendationsManager.loadMoreRecommendations();
}

function closePreviewModal() {
    recommendationsManager.closePreviewModal();
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    recommendationsManager = new RecommendationsManager();
});
