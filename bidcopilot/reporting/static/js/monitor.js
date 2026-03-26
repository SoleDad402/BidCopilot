/**
 * BidCopilot — Visual Pipeline Monitor
 * Real-time polling, animated SVG rings, live feed, adapter cards
 */
(function () {
    'use strict';

    var E = BC.esc;
    var CIRCUMFERENCE = 2 * Math.PI * 38; // r=38 in SVG
    var lastLogId = 0;
    var feedEntries = [];
    var MAX_FEED = 80;
    var pollTimer = null;
    var startTime = Date.now();

    // Adapter state tracking for visual progress
    var adapterState = {}; // {name: {status, found, latest}}
    var matchState = { current: 0, total: 0, matched: 0, rejected: 0 };

    // Score distribution accumulator
    var scoreBuckets = { '90-100': 0, '80-89': 0, '70-79': 0, '60-69': 0, '0-59': 0 };

    // ══════════════════════════════════════════════
    // PROGRESS RING
    // ══════════════════════════════════════════════
    function setRing(id, pct, color) {
        var el = document.getElementById(id);
        if (!el) return;
        var offset = CIRCUMFERENCE - (pct / 100) * CIRCUMFERENCE;
        el.style.strokeDashoffset = Math.max(offset, 0);
        if (color) el.setAttribute('stroke', color);
    }

    function setRingValue(id, val) {
        var el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    // ══════════════════════════════════════════════
    // STAGE STATUS
    // ══════════════════════════════════════════════
    function setStageStatus(stage, status, detail) {
        var card = document.getElementById('stage' + stage);
        var badge = document.getElementById('status' + stage);
        var detailEl = document.getElementById('detail' + stage);

        if (!card) return;

        card.className = 'stage-card';
        badge.className = 'stage-status';

        if (status === 'running') {
            card.classList.add('active');
            badge.classList.add('running');
            badge.textContent = 'Running';
        } else if (status === 'error') {
            card.classList.add('error');
            badge.classList.add('error');
            badge.textContent = 'Error';
        } else if (status === 'done' || status === 'idle') {
            if (detail && detail !== 'Waiting...') {
                card.classList.add('done');
                badge.classList.add('done');
                badge.textContent = 'Complete';
            } else {
                badge.classList.add('idle');
                badge.textContent = 'Idle';
            }
        }

        if (detail !== undefined) detailEl.textContent = detail;

        // Arrow activation
        var arrow1 = document.getElementById('arrow1');
        var arrow2 = document.getElementById('arrow2');
        if (stage === 'Discovery' && status === 'running') {
            arrow1.classList.add('active');
        } else if (stage === 'Discovery' && status !== 'running') {
            arrow1.classList.remove('active');
        }
        if (stage === 'Matching' && status === 'running') {
            arrow2.classList.add('active');
        } else if (stage === 'Matching' && status !== 'running') {
            arrow2.classList.remove('active');
        }
    }

    // ══════════════════════════════════════════════
    // DECORATIVE PARTICLES
    // ══════════════════════════════════════════════
    function initParticles() {
        ['Discovery', 'Matching', 'Application'].forEach(function (stage) {
            var container = document.getElementById('particles' + stage);
            if (!container || container.children.length > 0) return;
            for (var i = 0; i < 6; i++) {
                var p = document.createElement('div');
                p.className = 'particle';
                p.style.left = (15 + Math.random() * 70) + '%';
                p.style.bottom = (10 + Math.random() * 30) + '%';
                p.style.animationDelay = (Math.random() * 3) + 's';
                p.style.animationDuration = (2 + Math.random() * 2) + 's';
                container.appendChild(p);
            }
        });
    }

    // ══════════════════════════════════════════════
    // STATS
    // ══════════════════════════════════════════════
    function updateStats(stats) {
        if (!stats || !stats.jobs) return;
        var j = stats.jobs;
        BC.animateValue(document.getElementById('statTotal'), j.total);
        BC.animateValue(document.getElementById('statNew'), j.new);
        BC.animateValue(document.getElementById('statMatched'), j.matched);
        BC.animateValue(document.getElementById('statApplied'), j.applied);
        BC.animateValue(document.getElementById('statToday'), stats.today_applications);
        BC.animateValue(document.getElementById('statErrors'), j.errors);
    }

    // ══════════════════════════════════════════════
    // PIPELINE STATE
    // ══════════════════════════════════════════════
    function updatePipeline(pipeline) {
        if (!pipeline) return;

        // Discovery
        var disc = pipeline.discovery || {};
        var discStatus = disc.status || 'idle';
        var discDetail = 'Waiting...';
        if (discStatus === 'running') {
            var activeCount = Object.keys(adapterState).filter(function (k) { return adapterState[k].status === 'running'; }).length;
            var totalFound = Object.keys(adapterState).reduce(function (sum, k) { return sum + (adapterState[k].found || 0); }, 0);
            discDetail = activeCount + ' adapters active, ' + totalFound + ' jobs found';
            setRingValue('ringDiscoveryVal', totalFound);
            // Approximate progress: show found count as ring fill (cap at 100)
            setRing('ringDiscovery', Math.min(totalFound, 200) / 2, 'var(--purple)');
        } else if (disc.total_found !== undefined) {
            discDetail = disc.total_found + ' found, ' + disc.total_new + ' new';
            setRingValue('ringDiscoveryVal', disc.total_found || 0);
            setRing('ringDiscovery', 100, 'var(--success)');
        }
        setStageStatus('Discovery', discStatus, discDetail);

        // Matching
        var match = pipeline.matching || {};
        var matchStatus = match.status || 'idle';
        var matchDetail = 'Waiting...';
        if (matchStatus === 'running' && matchState.total > 0) {
            var pct = Math.round((matchState.current / matchState.total) * 100);
            matchDetail = matchState.current + '/' + matchState.total + ' scored (' + matchState.matched + ' matched)';
            setRingValue('ringMatchingVal', pct);
            setRing('ringMatching', pct, 'var(--blue)');
        } else if (matchStatus === 'idle' && match.last_run) {
            matchDetail = 'Last run: ' + BC.timeAgo(match.last_run);
            setRing('ringMatching', 100, 'var(--success)');
            setRingValue('ringMatchingVal', '100');
        }
        setStageStatus('Matching', matchStatus, matchDetail);

        // Application
        var app = pipeline.application || {};
        var appStatus = app.status || 'idle';
        setStageStatus('Application', appStatus, appStatus === 'error' ? (app.error || 'Error') : 'Waiting...');
    }

    // ══════════════════════════════════════════════
    // ADAPTERS PANEL
    // ══════════════════════════════════════════════
    function renderAdapters() {
        var container = document.getElementById('adapterList');
        var names = Object.keys(adapterState).sort();
        if (names.length === 0) {
            container.innerHTML = '<div class="feed-empty">No adapter activity yet</div>';
            document.getElementById('adapterSummary').textContent = '';
            return;
        }

        var running = 0, done = 0, errored = 0;
        var html = '';
        names.forEach(function (name) {
            var a = adapterState[name];
            var dotClass = a.status || 'idle';
            if (a.status === 'done') done++;
            else if (a.status === 'running') running++;
            else if (a.status === 'error') errored++;

            var barPct = 0;
            if (a.status === 'done') barPct = 100;
            else if (a.found > 0) barPct = Math.min(a.found * 2, 90); // approximate

            html += '<div class="adapter-row">' +
                '<div class="adapter-dot ' + dotClass + '"></div>' +
                '<div class="adapter-name">' + E(name) + '</div>' +
                '<div class="adapter-bar-wrap"><div class="adapter-bar" style="width:' + barPct + '%;background:' +
                (a.status === 'error' ? 'var(--error)' : a.status === 'done' ? 'var(--success)' : 'var(--accent)') +
                '"></div></div>' +
                '<div class="adapter-count">' + (a.found || 0) + '</div>' +
                '</div>';
        });
        container.innerHTML = html;
        document.getElementById('adapterSummary').textContent = running + ' running, ' + done + ' done' + (errored ? ', ' + errored + ' errors' : '');
    }

    // ══════════════════════════════════════════════
    // SCORE DISTRIBUTION
    // ══════════════════════════════════════════════
    function renderScores() {
        var container = document.getElementById('scoreDistribution');
        var total = Object.keys(scoreBuckets).reduce(function (s, k) { return s + scoreBuckets[k]; }, 0);
        if (total === 0) {
            container.innerHTML = '<div class="feed-empty">No match scores yet</div>';
            return;
        }
        var max = Math.max.apply(null, Object.keys(scoreBuckets).map(function (k) { return scoreBuckets[k]; }));
        if (max === 0) max = 1;

        var classes = { '90-100': 's90', '80-89': 's80', '70-79': 's70', '60-69': 's60', '0-59': 's0' };
        var html = '';
        Object.keys(scoreBuckets).forEach(function (range) {
            var count = scoreBuckets[range];
            var pct = Math.round((count / max) * 100);
            html += '<div class="score-bar-row">' +
                '<div class="score-label">' + range + '</div>' +
                '<div class="score-track"><div class="score-fill ' + classes[range] + '" style="width:' + pct + '%"></div></div>' +
                '<div class="score-count">' + count + '</div></div>';
        });
        container.innerHTML = html;
    }

    // ══════════════════════════════════════════════
    // LIVE FEED
    // ══════════════════════════════════════════════
    function addFeedEntry(entry) {
        feedEntries.unshift(entry);
        if (feedEntries.length > MAX_FEED) feedEntries.pop();
    }

    function renderFeed() {
        var container = document.getElementById('liveFeed');
        if (feedEntries.length === 0) {
            container.innerHTML = '<div class="feed-empty">No activity yet. Start a discovery or matching run.</div>';
            document.getElementById('feedCount').textContent = '0 events';
            return;
        }

        var html = '';
        feedEntries.forEach(function (e) {
            var r = formatFeedEntry(e);
            html += '<div class="feed-entry">' +
                '<div class="feed-icon ' + r.iconClass + '">' + r.icon + '</div>' +
                '<div class="feed-text">' + r.text + '</div>' +
                '<div class="feed-time">' + E((e.ts || '').substring(11, 19)) + '</div>' +
                '</div>';
        });
        container.innerHTML = html;
        document.getElementById('feedCount').textContent = feedEntries.length + ' events';
    }

    function formatFeedEntry(e) {
        var ev = e.event || '';
        var icon = '', iconClass = 'info', text = '';

        switch (ev) {
            case 'discovery_start':
                icon = 'S'; iconClass = 'discover';
                text = '<strong>Discovery started</strong> with ' + (e.total_adapters || '?') + ' adapters';
                break;
            case 'adapter_start':
                icon = 'A'; iconClass = 'discover';
                text = 'Scanning <strong>' + E(e.adapter) + '</strong>...';
                break;
            case 'adapter_progress':
                icon = 'P'; iconClass = 'discover';
                text = '<strong>' + E(e.adapter) + '</strong> found ' + (e.found || 0) + ' jobs';
                if (e.latest) text += ' &mdash; ' + E(e.latest);
                break;
            case 'adapter_done':
                icon = 'D'; iconClass = 'success';
                text = '<strong>' + E(e.adapter) + '</strong> complete &mdash; ' + (e.found || 0) + ' found, ' + (e.new || e['new'] || 0) + ' new';
                break;
            case 'adapter_error':
                icon = 'E'; iconClass = 'error';
                text = '<strong>' + E(e.adapter) + '</strong> error: ' + E(e.error || 'unknown');
                break;
            case 'discovery_done':
                icon = 'F'; iconClass = 'success';
                text = '<strong>Discovery finished</strong> &mdash; ' + (e.total_found || 0) + ' found, ' + (e.total_new || 0) + ' new';
                break;
            case 'matching_start':
                icon = 'M'; iconClass = 'match';
                text = '<strong>Matching started</strong> &mdash; ' + (e.total_jobs || 0) + ' jobs to score';
                break;
            case 'matching_progress':
                icon = 'S'; iconClass = 'match';
                var verdict = e.verdict === 'matched' ? '<span style="color:var(--success)">matched</span>' : '<span style="color:var(--text-dim)">rejected</span>';
                text = '<strong>' + E(e.latest || '') + '</strong> score: ' + (e.score || 0) + ' ' + verdict;
                break;
            case 'matching_done':
                icon = 'F'; iconClass = 'success';
                text = '<strong>Matching finished</strong> &mdash; ' + (e.matched || 0) + ' matched, ' + (e.rejected || 0) + ' rejected';
                break;
            case 'warn':
                icon = 'W'; iconClass = 'warn';
                text = E(e.message || '');
                break;
            default:
                icon = 'I'; iconClass = 'info';
                text = E(ev) + ' ' + E(e.detail || e.site || '');
        }

        return { icon: icon, iconClass: iconClass, text: text };
    }

    // ══════════════════════════════════════════════
    // PROCESS LOG EVENTS (update internal state)
    // ══════════════════════════════════════════════
    function processLogEntry(e) {
        var ev = e.event || '';

        switch (ev) {
            case 'discovery_start':
                adapterState = {};
                (e.adapters || []).forEach(function (name) {
                    adapterState[name] = { status: 'idle', found: 0, latest: '' };
                });
                break;
            case 'adapter_start':
                if (e.adapter) adapterState[e.adapter] = { status: 'running', found: 0, latest: '' };
                break;
            case 'adapter_progress':
                if (e.adapter && adapterState[e.adapter]) {
                    adapterState[e.adapter].found = e.found || 0;
                    adapterState[e.adapter].latest = e.latest || '';
                }
                break;
            case 'adapter_done':
                if (e.adapter && adapterState[e.adapter]) {
                    adapterState[e.adapter].status = 'done';
                    adapterState[e.adapter].found = e.found || 0;
                }
                break;
            case 'adapter_error':
                if (e.adapter) {
                    if (!adapterState[e.adapter]) adapterState[e.adapter] = {};
                    adapterState[e.adapter].status = 'error';
                }
                break;
            case 'matching_start':
                matchState = { current: 0, total: e.total_jobs || 0, matched: 0, rejected: 0 };
                break;
            case 'matching_progress':
                matchState.current = e.current || matchState.current;
                matchState.total = e.total || matchState.total;
                matchState.matched = e.matched || matchState.matched;
                matchState.rejected = e.rejected || matchState.rejected;
                // Update score buckets
                if (e.score !== undefined) {
                    var s = e.score;
                    if (s >= 90) scoreBuckets['90-100']++;
                    else if (s >= 80) scoreBuckets['80-89']++;
                    else if (s >= 70) scoreBuckets['70-79']++;
                    else if (s >= 60) scoreBuckets['60-69']++;
                    else scoreBuckets['0-59']++;
                }
                break;
            case 'matching_done':
                matchState.current = matchState.total;
                matchState.matched = e.matched || matchState.matched;
                matchState.rejected = e.rejected || matchState.rejected;
                break;
        }
    }

    // ══════════════════════════════════════════════
    // POLLING
    // ══════════════════════════════════════════════
    function poll() {
        // Stats + pipeline state
        fetch('/api/stats').then(function (r) { return r.json(); }).then(function (data) {
            updateStats(data);
            updatePipeline(data.pipeline);
        }).catch(function () {});

        // Live log
        fetch('/api/live-log?after=' + lastLogId).then(function (r) { return r.json(); }).then(function (data) {
            var entries = data.entries || [];
            if (entries.length === 0) return;

            entries.forEach(function (e) {
                lastLogId = Math.max(lastLogId, e.id);
                processLogEntry(e);
                addFeedEntry(e);
            });

            renderAdapters();
            renderScores();
            renderFeed();
        }).catch(function () {});

        // Uptime display
        var elapsed = Math.floor((Date.now() - startTime) / 1000);
        var m = Math.floor(elapsed / 60);
        var s = elapsed % 60;
        var uptimeEl = document.getElementById('monitorUptime');
        if (uptimeEl) uptimeEl.textContent = 'Monitoring: ' + m + 'm ' + s + 's';
    }

    // ══════════════════════════════════════════════
    // INITIAL LOAD: Get score distribution from analytics
    // ══════════════════════════════════════════════
    function loadInitialScores() {
        fetch('/api/admin/analytics').then(function (r) { return r.json(); }).then(function (data) {
            (data.score_distribution || []).forEach(function (item) {
                if (scoreBuckets[item.range] !== undefined) {
                    scoreBuckets[item.range] = item.count;
                }
            });
            renderScores();
        }).catch(function () {});
    }

    // ══════════════════════════════════════════════
    // INIT
    // ══════════════════════════════════════════════
    initParticles();
    loadInitialScores();
    poll();
    pollTimer = setInterval(poll, 1500);

    // Cleanup on page navigation
    window.addEventListener('beforeunload', function () {
        if (pollTimer) clearInterval(pollTimer);
    });

})();
