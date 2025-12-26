/**
 * DownMedia - YouTube Video & Audio Downloader
 * Frontend JavaScript
 */

document.addEventListener('DOMContentLoaded', () => {
    // ============================================
    // State Management
    // ============================================
    const state = {
        video: {
            url: '',
            info: null,
            jobId: null,
            progressInterval: null
        },
        audio: {
            url: '',
            info: null,
            jobId: null,
            progressInterval: null
        }
    };

    // ============================================
    // DOM Elements
    // ============================================
    const elements = {
        // Tabs
        tabBtns: document.querySelectorAll('.tab-btn'),
        tabContents: document.querySelectorAll('.tab-content'),

        // Video Tab
        video: {
            form: document.getElementById('videoSearchForm'),
            urlInput: document.getElementById('videoUrlInput'),
            fetchBtn: document.getElementById('videoFetchBtn'),
            error: document.getElementById('videoError'),
            errorText: document.getElementById('videoErrorText'),
            infoSection: document.getElementById('videoInfoSection'),
            thumbnail: document.getElementById('videoThumbnail'),
            title: document.getElementById('videoTitle'),
            channel: document.getElementById('videoChannel'),
            duration: document.getElementById('videoDuration'),
            views: document.getElementById('videoViews'),
            qualitySelect: document.getElementById('videoQualitySelect'),
            formatSelect: document.getElementById('videoFormatSelect'),
            downloadBtn: document.getElementById('videoDownloadBtn'),
            progressSection: document.getElementById('videoProgressSection'),
            progressBar: document.getElementById('videoProgressBar'),
            progressStatus: document.getElementById('videoProgressStatus'),
            progressPercent: document.getElementById('videoProgressPercent')
        },

        // Audio Tab
        audio: {
            form: document.getElementById('audioSearchForm'),
            urlInput: document.getElementById('audioUrlInput'),
            fetchBtn: document.getElementById('audioFetchBtn'),
            error: document.getElementById('audioError'),
            errorText: document.getElementById('audioErrorText'),
            infoSection: document.getElementById('audioInfoSection'),
            thumbnail: document.getElementById('audioThumbnail'),
            title: document.getElementById('audioTitle'),
            channel: document.getElementById('audioChannel'),
            duration: document.getElementById('audioDuration'),
            views: document.getElementById('audioViews'),
            qualitySelect: document.getElementById('audioQualitySelect'),
            formatSelect: document.getElementById('audioFormatSelect'),
            downloadBtn: document.getElementById('audioDownloadBtn'),
            progressSection: document.getElementById('audioProgressSection'),
            progressBar: document.getElementById('audioProgressBar'),
            progressStatus: document.getElementById('audioProgressStatus'),
            progressPercent: document.getElementById('audioProgressPercent')
        }
    };

    // ============================================
    // Utility Functions
    // ============================================
    function formatDuration(seconds) {
        if (!seconds) return '0:00';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) {
            return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        }
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    function formatViews(count) {
        if (!count) return '0 views';
        if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M views`;
        if (count >= 1000) return `${(count / 1000).toFixed(1)}K views`;
        return `${count} views`;
    }

    function formatBytes(bytes) {
        if (!bytes) return '';
        const mb = bytes / (1024 * 1024);
        return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`;
    }

    function showError(type, message) {
        const el = elements[type];
        el.errorText.textContent = message;
        el.error.classList.add('visible');
        setTimeout(() => {
            el.error.classList.remove('visible');
        }, 5000);
    }

    function hideError(type) {
        elements[type].error.classList.remove('visible');
    }

    function setLoading(type, isLoading) {
        const btn = elements[type].fetchBtn;
        if (isLoading) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Loading...';
        } else {
            btn.disabled = false;
            btn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                Get Info
            `;
        }
    }

    // ============================================
    // Tab Switching
    // ============================================
    elements.tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;

            // Update active tab button
            elements.tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update active tab content
            elements.tabContents.forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`${tab}Tab`).classList.add('active');
        });
    });

    // ============================================
    // Fetch Video/Audio Info
    // ============================================
    async function fetchInfo(type) {
        const el = elements[type];
        const url = el.urlInput.value.trim();

        if (!url) {
            showError(type, 'Please enter a URL');
            return;
        }

        hideError(type);
        setLoading(type, true);
        el.infoSection.classList.remove('visible');

        try {
            const response = await fetch('/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch video info');
            }

            // Store state
            state[type].url = url;
            state[type].info = data;

            // Update UI
            displayInfo(type, data);

        } catch (error) {
            console.error('Fetch error:', error);
            showError(type, error.message);
        } finally {
            setLoading(type, false);
        }
    }

    function displayInfo(type, data) {
        const el = elements[type];

        // Update thumbnail
        el.thumbnail.src = data.thumbnail || '';
        el.thumbnail.alt = data.title || 'Video thumbnail';

        // Update title
        el.title.textContent = data.title || 'Unknown Title';

        // Update meta info
        el.channel.querySelector('span').textContent = data.channel || 'Unknown Channel';
        el.duration.querySelector('span').textContent = formatDuration(data.duration);
        el.views.querySelector('span').textContent = formatViews(data.view_count);

        // Populate quality dropdown
        el.qualitySelect.innerHTML = '';
        
        const formats = type === 'video' ? data.video_formats : data.audio_formats;
        
        if (formats && formats.length > 0) {
            // Add "Best Available" option
            const bestOption = document.createElement('option');
            bestOption.value = 'best';
            bestOption.textContent = 'Best Available';
            el.qualitySelect.appendChild(bestOption);

            formats.forEach(fmt => {
                const option = document.createElement('option');
                option.value = fmt.format_id;
                const sizeInfo = fmt.filesize ? ` (${formatBytes(fmt.filesize)})` : '';
                option.textContent = `${fmt.quality}${sizeInfo}`;
                el.qualitySelect.appendChild(option);
            });
        } else {
            const option = document.createElement('option');
            option.value = 'best';
            option.textContent = 'Best Available';
            el.qualitySelect.appendChild(option);
        }

        // Show info section with animation
        el.infoSection.classList.add('visible');
    }

    // ============================================
    // Download Handling
    // ============================================
    async function startDownload(type) {
        const el = elements[type];
        const url = state[type].url;
        const formatId = el.qualitySelect.value;
        const outputFormat = el.formatSelect.value;

        if (!url) {
            showError(type, 'Please fetch video info first');
            return;
        }

        // Disable download button
        el.downloadBtn.disabled = true;
        el.downloadBtn.innerHTML = '<span class="spinner"></span> Starting...';

        // Show progress section
        el.progressSection.classList.add('visible');
        el.progressBar.style.width = '0%';
        el.progressPercent.textContent = '0%';
        el.progressStatus.textContent = 'Starting download...';

        try {
            const res = await fetch('/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url,
                    format_id: formatId,
                    mode: type,
                    output_format: outputFormat
                })
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.error || 'Failed to start download');
            }

            // Determine filename from Content-Disposition or fallback
            const cd = res.headers.get('Content-Disposition') || '';
            const match = /filename\*?=(?:UTF-8'')?["']?([^;"']+)["']?/i.exec(cd);
            let filename = match ? decodeURIComponent(match[1]) : null;
            if (!filename) {
                const info = state[type].info || {};
                const ext = (el.formatSelect.value || '').replace('.', '') || 'bin';
                const clean = (info.title || 'download').replace(/[^a-z0-9 \-_]/ig, '').slice(0,100);
                filename = `${clean || 'download'}.${ext}`;
            }

            const contentLength = parseInt(res.headers.get('Content-Length') || '0', 10);
            const contentType = res.headers.get('Content-Type') || 'application/octet-stream';

            // Stream and report progress
            const reader = res.body.getReader();
            const chunks = [];
            let received = 0;
            el.progressStatus.textContent = 'Downloading...';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                chunks.push(value);
                received += value.length;
                if (contentLength) {
                    const percent = Math.min(100, Math.round((received / contentLength) * 100));
                    el.progressBar.style.width = `${percent}%`;
                    el.progressPercent.textContent = `${percent}%`;
                } else {
                    // indeterminate progress animation fallback
                    el.progressBar.style.width = '50%';
                    el.progressPercent.textContent = `${Math.min(99, Math.round(received / 1024))}%`;
                }
            }

            // Build blob and trigger download
            const blob = new Blob(chunks, { type: contentType });
            const urlObj = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = urlObj;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(urlObj);

            el.progressBar.style.width = '100%';
            el.progressPercent.textContent = '100%';
            el.progressStatus.textContent = 'Download complete';

            setTimeout(() => resetDownloadUI(type), 1500);

        } catch (error) {
            console.error('Download error:', error);
            showError(type, error.message || 'Download failed');
            resetDownloadUI(type);
        }
    }

    function trackProgress(type, jobId) {
        // no-op: server streams directly so tracking via job id is not used
        return;
    }

    function resetDownloadUI(type) {
        const el = elements[type];
        
        el.downloadBtn.disabled = false;
        const icon = type === 'video' ? 'Download Video' : 'Download Audio';
        el.downloadBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            ${icon}
        `;

        setTimeout(() => {
            el.progressSection.classList.remove('visible');
            el.progressBar.style.width = '0%';
            el.progressPercent.textContent = '0%';
        }, 2000);
    }

    // ============================================
    // Event Listeners
    // ============================================
    
    // Video form submit
    elements.video.form.addEventListener('submit', (e) => {
        e.preventDefault();
        fetchInfo('video');
    });

    // Audio form submit
    elements.audio.form.addEventListener('submit', (e) => {
        e.preventDefault();
        fetchInfo('audio');
    });

    // Video download button
    elements.video.downloadBtn.addEventListener('click', () => {
        startDownload('video');
    });

    // Audio download button
    elements.audio.downloadBtn.addEventListener('click', () => {
        startDownload('audio');
    });

    // Enter key on URL inputs
    elements.video.urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            fetchInfo('video');
        }
    });

    elements.audio.urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            fetchInfo('audio');
        }
    });

    // ============================================
    // Modal Handlers (Placeholders)
    // ============================================
    document.getElementById('howToUseBtn')?.addEventListener('click', () => {
        alert('How to Use:\n\n1. Paste a YouTube video URL\n2. Click "Get Info" to fetch video details\n3. Select your preferred quality and format\n4. Click "Download" to start downloading');
    });

    document.getElementById('aboutBtn')?.addEventListener('click', () => {
        alert('DownMedia - YouTube Downloader\n\nA simple and fast way to download YouTube videos and audio.\n\nBuilt with Flask & yt-dlp');
    });

    document.getElementById('loginBtn')?.addEventListener('click', () => {
        alert('Login functionality coming soon!');
    });

    // ============================================
    // Initialize
    // ============================================
    console.log('DownMedia initialized successfully!');
});
