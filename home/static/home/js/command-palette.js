/**
 * Pumzika Command Palette with LLM Chat
 * 
 * A keyboard-driven command palette for the NLP Review Analytics system.
 * Activated with Ctrl+K (or Cmd+K on Mac).
 * 
 * Features:
 * - Quick navigation to dashboard sections
 * - Trigger NLP operations (sentiment analysis, topic extraction, insight generation)
 * - LLM-powered chat for natural language queries about hotel data
 * - Real-time status updates
 */

(function() {
    'use strict';

    const CONFIG = {
        apiEndpoint: '/admin/home/api/command-palette/',
        chatEndpoint: '/admin/home/api/chat/',
        dashboardUrl: '/admin/home/dashboard/',
        reviewsUrl: '/admin/home/review/',
        topicsUrl: '/admin/home/topiccluster/',
        insightsUrl: '/admin/home/propertyinsight/',
        snapshotsUrl: '/admin/home/sentimentsnapshot/',
    };

    const COMMANDS = [
        { id: 'dashboard', title: '📊 Open Dashboard', description: 'View sentiment analytics dashboard', category: 'Navigation', action: () => window.location.href = CONFIG.dashboardUrl },
        { id: 'reviews', title: '📝 View All Reviews', description: 'Browse and search all reviews', category: 'Navigation', action: () => window.location.href = CONFIG.reviewsUrl },
        { id: 'topics', title: '🏷️ View Topic Clusters', description: 'See discovered topics and their sentiment', category: 'Navigation', action: () => window.location.href = CONFIG.topicsUrl },
        { id: 'insights', title: '💡 View Property Insights', description: 'See AI-generated property insights', category: 'Navigation', action: () => window.location.href = CONFIG.insightsUrl },
        { id: 'snapshots', title: '📈 View Sentiment Snapshots', description: 'See daily sentiment trends', category: 'Navigation', action: () => window.location.href = CONFIG.snapshotsUrl },
        { id: 'analyze_sentiment', title: '🤖 Analyze Sentiment', description: 'Run NLP sentiment analysis on unprocessed reviews', category: 'NLP Operations', action: () => executeCommand('analyze_sentiment', { async: true, batch_size: 100 }) },
        { id: 'extract_topics', title: '🏷️ Extract Topics', description: 'Run topic extraction on processed reviews', category: 'NLP Operations', action: () => executeCommand('extract_topics', { async: true, update_clusters: true }) },
        { id: 'generate_insights', title: '💡 Generate Insights', description: 'Generate AI-powered property insights', category: 'NLP Operations', action: () => executeCommand('generate_insights', { async: true, all: true }) },
        { id: 'update_clusters', title: '🔄 Update Topic Clusters', description: 'Rebuild topic cluster aggregates', category: 'NLP Operations', action: () => executeCommand('update_clusters', {}) },
        { id: 'build_snapshots', title: '📊 Build Sentiment Snapshots', description: 'Generate daily sentiment aggregates', category: 'NLP Operations', action: () => executeCommand('build_snapshots', {}) },
        { id: 'status', title: '📋 Show System Status', description: 'View NLP processing statistics', category: 'System', action: () => showStatus() },
        { id: 'refresh_status', title: '🔄 Refresh Status', description: 'Update status display', category: 'System', action: () => fetchStatus() },
    ];

    const CHAT_SUGGESTIONS = [
        "What are the best hotels?",
        "Which hotels have the worst cleanliness?",
        "Show me hotels with great staff",
        "What do guests complain about most?",
        "Best value for money hotels",
        "Hotels with noise issues",
        "Top rated hotels in Amsterdam",
        "Hotels with poor WiFi",
    ];

    let palette, overlay, input, resultsList, statusPanel;
    let currentResults = [], selectedIndex = 0, isChatMode = false, chatHistory = [];

    function init() {
        createPalette();
        bindEvents();
        fetchStatus();
        console.log('🎨 Pumzika Command Palette initialized. Press Ctrl+K to open.');
    }

    function createPalette() {
        overlay = document.createElement('div');
        overlay.id = 'pumzika-palette-overlay';
        overlay.style.cssText = 'display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:99999;backdrop-filter:blur(4px);';

        palette = document.createElement('div');
        palette.id = 'pumzika-palette';
        palette.style.cssText = 'display:none;position:fixed;top:15%;left:50%;transform:translateX(-50%);width:700px;max-width:90vw;max-height:75vh;background:var(--color-background-paper,#fff);border:1px solid var(--color-border-primary,#e0e0e0);border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);z-index:100000;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;';

        const inputContainer = document.createElement('div');
        inputContainer.style.cssText = 'padding:16px 20px;border-bottom:1px solid var(--color-border-primary,#e0e0e0);';

        input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Type a command or ask a question...';
        input.style.cssText = 'width:100%;border:none;outline:none;font-size:16px;font-family:inherit;background:transparent;color:var(--color-text-primary,#333);';
        inputContainer.appendChild(input);

        const suggestionsContainer = document.createElement('div');
        suggestionsContainer.id = 'pumzika-suggestions';
        suggestionsContainer.style.cssText = 'padding:8px 20px;display:none;flex-wrap:wrap;gap:6px;border-bottom:1px solid var(--color-border-primary,#e0e0e0);';
        CHAT_SUGGESTIONS.forEach(suggestion => {
            const btn = document.createElement('button');
            btn.textContent = suggestion;
            btn.style.cssText = 'padding:4px 12px;background:var(--color-background-default,#f5f5f5);border:1px solid var(--color-border-primary,#e0e0e0);border-radius:16px;font-size:12px;cursor:pointer;white-space:nowrap;transition:all 0.2s;';
            btn.onmouseenter = () => { btn.style.background = 'var(--color-primary,#1565c0)'; btn.style.color = '#fff'; };
            btn.onmouseleave = () => { btn.style.background = ''; btn.style.color = ''; };
            btn.onclick = () => { input.value = suggestion; handleChatQuery(suggestion); };
            suggestionsContainer.appendChild(btn);
        });
        inputContainer.appendChild(suggestionsContainer);

        resultsList = document.createElement('div');
        resultsList.id = 'pumzika-results';
        resultsList.style.cssText = 'max-height:450px;overflow-y:auto;padding:8px 0;';

        statusPanel = document.createElement('div');
        statusPanel.id = 'pumzika-status';
        statusPanel.style.cssText = 'padding:12px 20px;border-top:1px solid var(--color-border-primary,#e0e0e0);background:var(--color-background-default,#f5f5f5);font-size:12px;color:var(--color-text-secondary,#666);display:flex;justify-content:space-between;align-items:center;';
        statusPanel.innerHTML = '<span>📊 Loading status...</span><span>Press Ctrl+K to close</span>';

        palette.appendChild(inputContainer);
        palette.appendChild(resultsList);
        palette.appendChild(statusPanel);
        overlay.appendChild(palette);
        document.body.appendChild(overlay);
    }

    function bindEvents() {
        document.addEventListener('keydown', e => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); togglePalette(); }
        });
        overlay.addEventListener('click', e => { if (e.target === overlay) closePalette(); });
        input.addEventListener('input', handleInput);
        input.addEventListener('keydown', handleKeydown);
        document.addEventListener('keydown', e => { if (e.key === 'Escape' && isPaletteOpen()) closePalette(); });
    }

    function togglePalette() { isPaletteOpen() ? closePalette() : openPalette(); }
    function isPaletteOpen() { return overlay && overlay.style.display === 'flex'; }

    function openPalette() {
        overlay.style.display = 'flex';
        overlay.style.alignItems = 'center';
        overlay.style.justifyContent = 'center';
        palette.style.display = 'block';
        input.value = '';
        input.focus();
        selectedIndex = 0;
        isChatMode = false;
        showSuggestions(true);
        filterCommands('');
    }

    function closePalette() {
        overlay.style.display = 'none';
        palette.style.display = 'none';
        input.value = '';
        input.blur();
        isChatMode = false;
    }

    function showSuggestions(show) {
        const suggestions = document.getElementById('pumzika-suggestions');
        if (suggestions) suggestions.style.display = show ? 'flex' : 'none';
    }

    function handleInput(e) {
        const query = e.target.value.toLowerCase().trim();
        selectedIndex = 0;
        
        // English question patterns
        const englishPatterns = [
            'what', 'which', 'how', 'show', 'tell', 'best', 'worst',
            'where', 'when', 'who', 'why', 'find', 'list', 'get'
        ];
        
        // Swahili question patterns for hotel queries
        const swahiliPatterns = [
            'hoteli', 'bora', 'nzuri', 'mbaya', 'chafu', 'vibaya',
            'usafi', 'safi', 'wafanyakazi', 'huduma', 'eneo', 'mahali',
            'bei', 'gharama', 'wifi', 'intaneti', 'chakula', 'kiamshakinywa',
            'kelele', 'utulivu', 'malalamiko'
        ];
        
        const isQuestion = query.length > 3 && (
            englishPatterns.some(p => query.startsWith(p)) ||
            swahiliPatterns.some(p => query.includes(p)) ||
            query.endsWith('?')
        );
        
        if (isQuestion) {
            isChatMode = true;
            showSuggestions(false);
            clearTimeout(this._chatTimeout);
            this._chatTimeout = setTimeout(() => handleChatQuery(e.target.value), 500);
        } else {
            isChatMode = false;
            showSuggestions(query.length === 0);
            filterCommands(query);
        }
    }

    function handleKeydown(e) {
        const items = resultsList.querySelectorAll('.pumzika-command-item');
        if (e.key === 'ArrowDown') { e.preventDefault(); selectedIndex = Math.min(selectedIndex + 1, items.length - 1); updateSelection(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); selectedIndex = Math.max(selectedIndex - 1, 0); updateSelection(); }
        else if (e.key === 'Enter') { e.preventDefault(); if (isChatMode && input.value.trim()) handleChatQuery(input.value.trim()); else if (items[selectedIndex]) items[selectedIndex].click(); }
    }

    function updateSelection() {
        const items = resultsList.querySelectorAll('.pumzika-command-item');
        items.forEach((item, index) => {
            item.style.background = index === selectedIndex ? 'var(--color-primary,#1565c0)' : '';
            item.style.color = index === selectedIndex ? '#fff' : '';
        });
        if (items[selectedIndex]) items[selectedIndex].scrollIntoView({ block: 'nearest' });
    }

    function filterCommands(query) {
        currentResults = COMMANDS.filter(cmd => {
            if (!query) return true;
            return cmd.title.toLowerCase().includes(query) || cmd.description.toLowerCase().includes(query) || cmd.category.toLowerCase().includes(query) || cmd.id.toLowerCase().includes(query);
        });
        renderResults();
    }

    function renderResults() {
        if (currentResults.length === 0) {
            resultsList.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--color-text-secondary,#666);"><div style="font-size:24px;margin-bottom:8px;">🔍</div><div>No commands found</div></div>';
            return;
        }
        const grouped = {};
        currentResults.forEach(cmd => { if (!grouped[cmd.category]) grouped[cmd.category] = []; grouped[cmd.category].push(cmd); });
        let html = '';
        Object.entries(grouped).forEach(([category, commands]) => {
            html += '<div style="padding:8px 20px 4px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;color:var(--color-text-secondary,#666);">' + category + '</div>';
            commands.forEach(cmd => {
                html += '<div class="pumzika-command-item" data-id="' + cmd.id + '" style="padding:10px 20px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;transition:background 0.1s ease;" onmouseenter="this.style.background=\'var(--color-hover,#f5f5f5)\'" onmouseleave="this.style.background=\'\'"><div><div style="font-weight:500;">' + cmd.title + '</div><div style="font-size:12px;color:var(--color-text-secondary,#666);margin-top:2px;">' + cmd.description + '</div></div><div style="font-size:11px;color:var(--color-text-tertiary,#999);">↵</div></div>';
            });
        });
        resultsList.innerHTML = html;
        resultsList.querySelectorAll('.pumzika-command-item').forEach(item => {
            item.addEventListener('click', () => {
                const cmd = COMMANDS.find(c => c.id === item.dataset.id);
                if (cmd) { closePalette(); cmd.action(); }
            });
        });
        updateSelection();
    }

    function handleChatQuery(query) {
        if (!query.trim()) return;
        showChatLoading();
        chatHistory.push({ role: 'user', content: query });
        fetch(CONFIG.chatEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ query: query, history: chatHistory.slice(-5) }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderChatResponse(data.response, data.data);
                chatHistory.push({ role: 'assistant', content: data.response });
            } else {
                renderChatError(data.error || 'Failed to get response');
            }
        })
        .catch(error => renderChatError('Network error: ' + error.message));
    }

    function showChatLoading() {
        resultsList.innerHTML = '<div style="padding:30px 20px;text-align:center;"><div style="display:inline-block;width:24px;height:24px;border:3px solid var(--color-border-primary,#e0e0e0);border-top-color:var(--color-primary,#1565c0);border-radius:50%;animation:spin 1s linear infinite;"></div><div style="margin-top:12px;color:var(--color-text-secondary,#666);">🤖 Analyzing your question...</div></div>';
    }

    function renderChatResponse(response, data) {
        let html = '<div style="padding:16px 20px;">';
        html += '<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:16px;">';
        html += '<div style="width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;align-items:center;justify-content:center;flex-shrink:0;"><span style="color:#fff;font-size:16px;">🤖</span></div>';
        html += '<div style="flex:1;"><div style="font-size:14px;line-height:1.6;color:var(--color-text-primary,#333);">' + response + '</div></div>';
        html += '</div>';

        // Render data visualizations if provided
        if (data && data.hotels) {
            html += '<div style="margin-top:12px;">';
            data.hotels.slice(0, 5).forEach((hotel, i) => {
                // Support both avg_score (for best/worst) and aspect_score (for aspect queries)
                const score = hotel.avg_score !== undefined ? hotel.avg_score : (hotel.aspect_score || 0);
                const scoreDisplay = score >= 1 ? score.toFixed(1) : (score * 100).toFixed(0) + '%';
                const scoreColor = score >= 0.8 ? '#2e7d32' : score >= 0.6 ? '#e65100' : '#c62828';
                html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:var(--color-background-default,#f5f5f5);border-radius:8px;margin-bottom:4px;">';
                html += '<span style="font-size:13px;font-weight:500;">' + (i + 1) + '. ' + hotel.name + '</span>';
                html += '<span style="color:' + scoreColor + ';font-weight:600;font-size:13px;">' + scoreDisplay + '</span>';
                html += '</div>';
            });
            html += '</div>';
        }

        html += '</div>';
        resultsList.innerHTML = html;
    }

    function renderChatError(error) {
        resultsList.innerHTML = '<div style="padding:30px 20px;text-align:center;color:var(--color-text-secondary,#666);"><div style="font-size:24px;margin-bottom:8px;">😕</div><div>' + error + '</div></div>';
    }

    function executeCommand(command, params) {
        showNotification('⚡ Executing command...', 'info');
        fetch(CONFIG.apiEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ command, params }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification('✅ ' + data.message, 'success');
                if (data.task_id) showNotification('📋 Task ID: ' + data.task_id, 'info');
                fetchStatus();
            } else {
                showNotification('❌ Error: ' + data.error, 'error');
            }
        })
        .catch(error => showNotification('❌ Network error: ' + error.message, 'error'));
    }

    function showStatus() { fetchStatus(); showNotification('📊 Status updated - check the status bar', 'info'); }

    function fetchStatus() {
        fetch(CONFIG.apiEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ command: 'get_status', params: {} }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && statusPanel) {
                const stats = data.data;
                statusPanel.innerHTML = '<span>📊 ' + stats.reviews.processed.toLocaleString() + '/' + stats.reviews.total.toLocaleString() + ' processed (' + stats.reviews.processing_rate + '%) | 🌍 ' + stats.languages.swahili + ' Swahili | 🏷️ ' + stats.topics.clusters + ' topics | 💡 ' + stats.insights.generated + ' insights</span><span>Ctrl+K to close</span>';
            }
        })
        .catch(error => console.error('Status fetch error:', error));
    }

    function showNotification(message, type) {
        const toast = document.createElement('div');
        toast.style.cssText = 'position:fixed;bottom:24px;right:24px;padding:12px 20px;background:' + (type === 'success' ? '#2e7d32' : type === 'error' ? '#c62828' : '#1565c0') + ';color:#fff;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.2);z-index:100001;font-size:14px;max-width:400px;animation:slideIn 0.3s ease;';
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => { toast.style.animation = 'slideOut 0.3s ease'; setTimeout(() => toast.remove(), 300); }, 3000);
    }

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Add animation styles
    const style = document.createElement('style');
    style.textContent = '@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}@keyframes slideOut{from{transform:translateX(0);opacity:1}to{transform:translateX(100%);opacity:0}}';
    document.head.appendChild(style);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();