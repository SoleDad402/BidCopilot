/**
 * BidCopilot — Admin Dashboard JS
 */
(function () {
    'use strict';

    var E = BC.esc;
    var BAR_COLORS = ['var(--accent)', 'var(--blue)', 'var(--success)', 'var(--purple)', 'var(--warning)', 'var(--cyan)', 'var(--orange)', 'var(--violet)'];

    // ── Section toggle (reuse profile pattern) ──
    function toggleSection(header) {
        var card = header.closest('.section-card');
        var id = card.dataset.section;
        card.classList.toggle('collapsed');
        var collapsed = JSON.parse(localStorage.getItem('bc_admin_collapsed') || '{}');
        collapsed[id] = card.classList.contains('collapsed');
        localStorage.setItem('bc_admin_collapsed', JSON.stringify(collapsed));
    }
    window.toggleSection = toggleSection;

    function restoreCollapse() {
        var collapsed = JSON.parse(localStorage.getItem('bc_admin_collapsed') || '{}');
        Object.keys(collapsed).forEach(function (id) {
            if (collapsed[id]) {
                var card = document.querySelector('.section-card[data-section="' + id + '"]');
                if (card) card.classList.add('collapsed');
            }
        });
    }

    // ── Helpers ──
    function infoItem(label, value, cls) {
        return '<div class="info-item"><div class="info-label">' + E(label) + '</div>' +
            '<div class="info-value' + (cls ? ' ' + cls : '') + '">' + value + '</div></div>';
    }

    function statusPill(ok, yesText, noText) {
        return '<span class="status-pill ' + (ok ? 'ok' : 'fail') + '">' +
            '<span style="width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block"></span>' +
            (ok ? (yesText || 'Connected') : (noText || 'Unreachable')) + '</span>';
    }

    function barChart(items, colorKey) {
        if (!items || items.length === 0) return '<div class="log-empty">No data</div>';
        var max = Math.max.apply(null, items.map(function (i) { return i.count; }));
        if (max === 0) max = 1;
        var html = '<div class="bar-chart">';
        items.forEach(function (item, idx) {
            var pct = Math.round((item.count / max) * 100);
            var color = BAR_COLORS[idx % BAR_COLORS.length];
            html += '<div class="bar-row">' +
                '<div class="bar-label">' + E(item.label) + '</div>' +
                '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:' + color + '"></div></div>' +
                '<div class="bar-count">' + item.count + '</div></div>';
        });
        html += '</div>';
        return html;
    }

    // ── 1. System Health ──
    function loadSystemHealth() {
        BC.api('/api/admin/system-health').then(function (d) {
            document.getElementById('systemHealthContent').innerHTML =
                '<div class="info-grid">' +
                infoItem('CVCopilot', statusPill(d.cvcopilot_reachable)) +
                infoItem('CVCopilot URL', E(d.cvcopilot_url)) +
                infoItem('Uptime', E(d.uptime_human)) +
                infoItem('Database Size', E(d.db_size_human)) +
                infoItem('Last Discovery', d.last_discovery_time ? BC.timeAgo(d.last_discovery_time) : 'Never') +
                infoItem('Python', E(d.python_version)) +
                infoItem('Platform', E(d.platform)) +
                infoItem('Auth', statusPill(d.auth_enabled, 'Enabled', 'Disabled')) +
                '</div>';
        });
    }

    // ── 2. User Info ──
    function loadUserInfo() {
        BC.api('/api/admin/user-info').then(function (d) {
            var u = d.user || {};
            document.getElementById('userInfoContent').innerHTML =
                '<div class="info-grid">' +
                infoItem('Name', E(u.full_name || u.email || 'N/A')) +
                infoItem('Email', E(u.email || 'N/A')) +
                infoItem('User ID', E(u.id || 'N/A')) +
                infoItem('Token', E(d.token_preview || 'None')) +
                infoItem('Session Cookie', E(d.session_cookie)) +
                infoItem('Auth Enabled', d.auth_enabled ? 'Yes' : 'No') +
                '</div>';
        });
    }

    // ── 3. API Keys ──
    function loadApiKeys() {
        BC.api('/api/admin/api-keys').then(function (d) {
            var html = '<div class="info-grid">';
            (d.keys || []).forEach(function (k) {
                var val = k.is_set
                    ? '<span style="color:var(--success)">' + E(k.masked) + '</span>'
                    : '<span style="color:var(--error)">Not set</span>';
                html += infoItem(k.name + ' (' + k.env_var + ')', val);
            });
            html += '</div>';
            document.getElementById('apiKeysContent').innerHTML = html;
        });
    }

    // ── 4. Discovery Monitoring ──
    function loadDiscovery() {
        BC.api('/api/admin/discovery-health').then(function (d) {
            var html = '<table class="admin-table"><thead><tr>' +
                '<th>Adapter</th><th>Enabled</th><th>Runs</th><th>Success</th><th>Fail</th><th>Error %</th><th>Last Run</th><th>Last Found</th>' +
                '</tr></thead><tbody>';
            (d.adapters || []).forEach(function (a) {
                html += '<tr>' +
                    '<td class="name">' + E(a.name) + '</td>' +
                    '<td>' + (a.enabled ? '<span style="color:var(--success)">Yes</span>' : '<span style="color:var(--text-dim)">No</span>') + '</td>' +
                    '<td class="num">' + a.total_runs + '</td>' +
                    '<td class="num" style="color:var(--success)">' + a.successful_runs + '</td>' +
                    '<td class="num" style="color:' + (a.failed_runs > 0 ? 'var(--error)' : 'var(--text-dim)') + '">' + a.failed_runs + '</td>' +
                    '<td class="num">' + (a.error_rate * 100).toFixed(1) + '%</td>' +
                    '<td>' + (a.last_run_time ? BC.timeAgo(a.last_run_time) : '-') + '</td>' +
                    '<td class="num">' + a.last_jobs_found + '</td>' +
                    '</tr>';
            });
            html += '</tbody></table>';
            document.getElementById('discoveryContent').innerHTML = html;
        });
    }

    // ── 5. Logs ──
    function loadLogs() {
        BC.api('/api/admin/logs?limit=100').then(function (d) {
            var entries = d.entries || [];
            if (entries.length === 0) {
                document.getElementById('logsContent').innerHTML = '<div class="log-empty">No log entries yet. Run discovery or matching to generate logs.</div>';
                return;
            }
            var html = '<div class="admin-actions"><button class="btn-admin" onclick="window.adminClearLogs()">Clear Logs</button></div><div class="log-list">';
            entries.reverse().forEach(function (e) {
                var isErr = (e.event || '').indexOf('error') !== -1 || (e.event || '').indexOf('fail') !== -1;
                html += '<div class="log-entry' + (isErr ? ' error' : '') + '">' +
                    '<span class="log-time">' + E((e.ts || '').substring(11, 19)) + '</span>' +
                    '<span class="log-event">' + E(e.event || '') + ' ' + E(e.site || e.detail || '') + '</span></div>';
            });
            html += '</div>';
            document.getElementById('logsContent').innerHTML = html;
        });
    }
    window.adminClearLogs = function () {
        BC.api('/api/live-log/clear', { method: 'POST' }).then(function () {
            loadLogs();
            BC.showToast('Logs cleared', 'success');
        });
    };

    // ── 6. Configuration ──
    var _configData = {};
    function loadConfig() {
        BC.api('/api/admin/config').then(function (d) {
            _configData = d;
            var html = '<div style="margin-bottom:16px"><div class="info-label" style="margin-bottom:8px">ENABLED SITES</div><div class="site-toggle-grid" id="siteToggles">';
            (d.all_available_sites || []).forEach(function (site) {
                var active = (d.enabled_sites || []).indexOf(site) !== -1;
                html += '<label class="site-toggle' + (active ? ' active' : '') + '">' +
                    '<input type="checkbox" value="' + E(site) + '"' + (active ? ' checked' : '') + ' onchange="window.adminToggleSite(this)">' +
                    E(site) + '</label>';
            });
            html += '</div></div>';

            html += '<div class="config-grid">' +
                configInput('Min Match Score', 'cfgMinScore', d.matching.min_match_score, 'number') +
                configInput('Skills Boost', 'cfgSkillBoost', d.matching.preferred_skills_boost, 'number') +
                configInput('Max Workers', 'cfgMaxWorkers', d.workers.max_workers, 'number') +
                configInput('Per-Site Limit', 'cfgPerSite', d.workers.per_site_limit, 'number') +
                configInput('Max Apps/Day', 'cfgMaxApps', d.workers.max_applications_per_day, 'number') +
                configInput('LLM Model', 'cfgModel', d.llm.model, 'text') +
                configInput('Temperature', 'cfgTemp', d.llm.temperature, 'number') +
                configInput('Max Tokens', 'cfgMaxTokens', d.llm.max_tokens, 'number') +
                '</div>';

            html += '<div class="admin-actions"><button class="btn-admin primary" onclick="window.adminSaveConfig()">Save Configuration</button></div>';
            document.getElementById('configContent').innerHTML = html;
        });
    }

    function configInput(label, id, value, type) {
        return '<div class="config-group"><label for="' + id + '">' + E(label) + '</label>' +
            '<input type="' + type + '" id="' + id + '" value="' + E(String(value)) + '"' +
            (type === 'number' ? ' step="any"' : '') + '></div>';
    }

    window.adminToggleSite = function (cb) {
        cb.parentElement.classList.toggle('active', cb.checked);
    };

    window.adminSaveConfig = function () {
        var enabledSites = [];
        document.querySelectorAll('#siteToggles input:checked').forEach(function (cb) {
            enabledSites.push(cb.value);
        });
        var payload = {
            enabled_sites: enabledSites,
            matching: {
                min_match_score: Number(document.getElementById('cfgMinScore').value),
                preferred_skills_boost: Number(document.getElementById('cfgSkillBoost').value)
            },
            workers: {
                max_workers: Number(document.getElementById('cfgMaxWorkers').value),
                per_site_limit: Number(document.getElementById('cfgPerSite').value),
                max_applications_per_day: Number(document.getElementById('cfgMaxApps').value)
            },
            llm: {
                model: document.getElementById('cfgModel').value,
                temperature: Number(document.getElementById('cfgTemp').value),
                max_tokens: Number(document.getElementById('cfgMaxTokens').value)
            }
        };
        BC.api('/api/admin/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function () {
            BC.showToast('Configuration saved', 'success');
        });
    };

    // ── 7. Analytics ──
    function loadAnalytics() {
        BC.api('/api/admin/analytics').then(function (d) {
            var html = '';

            // Jobs by status
            html += '<div class="info-label" style="padding-top:16px;margin-bottom:4px">JOBS BY STATUS</div>';
            html += barChart((d.jobs_by_status || []).map(function (i) { return { label: i.status, count: i.count }; }));

            // Jobs by source
            html += '<div class="info-label" style="padding-top:20px;margin-bottom:4px">JOBS BY SOURCE</div>';
            html += barChart((d.jobs_by_source || []).map(function (i) { return { label: i.site, count: i.count }; }));

            // Score distribution
            html += '<div class="info-label" style="padding-top:20px;margin-bottom:4px">MATCH SCORE DISTRIBUTION</div>';
            html += barChart((d.score_distribution || []).map(function (i) { return { label: i.range, count: i.count }; }));

            // Daily discoveries
            var disc = d.daily_discoveries || [];
            if (disc.length > 0) {
                html += '<div class="info-label" style="padding-top:20px;margin-bottom:4px">DAILY DISCOVERIES (LAST 30 DAYS)</div>';
                html += barChart(disc.slice(-14).map(function (i) { return { label: i.date.substring(5), count: i.count }; }));
            }

            // Daily applications
            var apps = d.daily_applications || [];
            if (apps.length > 0) {
                html += '<div class="info-label" style="padding-top:20px;margin-bottom:4px">DAILY APPLICATIONS</div>';
                html += barChart(apps.slice(-14).map(function (i) { return { label: i.date.substring(5), count: i.count }; }));
            }

            document.getElementById('analyticsContent').innerHTML = html || '<div class="log-empty">No analytics data yet</div>';
        });
    }

    // ── 8. Database ──
    function loadDatabase() {
        BC.api('/api/admin/database').then(function (d) {
            var html = '<div class="info-grid">' +
                infoItem('Path', E(d.db_path)) +
                infoItem('Size', E(d.db_size_human)) +
                '</div>';

            html += '<table class="admin-table"><thead><tr><th>Table</th><th style="text-align:right">Rows</th></tr></thead><tbody>';
            (d.tables || []).forEach(function (t) {
                html += '<tr><td class="name">' + E(t.name) + '</td><td class="num">' + t.row_count + '</td></tr>';
            });
            html += '</tbody></table>';

            html += '<div class="admin-actions">' +
                '<button class="btn-admin" onclick="window.adminVacuum()">Vacuum Database</button>' +
                '<a href="/api/admin/database/export" class="btn-admin" download>Export Database</a>' +
                '</div>';

            document.getElementById('databaseContent').innerHTML = html;
        });
    }
    window.adminVacuum = function () {
        BC.api('/api/admin/database/vacuum', { method: 'POST' }).then(function (d) {
            BC.showToast('Vacuum complete: ' + d.size_before + ' -> ' + d.size_after, 'success');
            loadDatabase();
        });
    };

    // ── 9. Credentials ──
    function loadCredentials() {
        BC.api('/api/admin/credentials').then(function (d) {
            var creds = d.credentials || [];
            var html = '';
            if (creds.length === 0) {
                html += '<div class="log-empty">No stored credentials</div>';
            } else {
                creds.forEach(function (c) {
                    html += '<div class="cred-row">' +
                        '<div class="cred-info"><span class="cred-site">' + E(c.site_name) + '</span>' +
                        '<span class="cred-user">' + E(c.username) + '</span>' +
                        (c.has_totp ? ' <span class="status-pill ok" style="font-size:0.625rem;padding:1px 6px">2FA</span>' : '') +
                        (c.has_cookies ? ' <span class="status-pill warn" style="font-size:0.625rem;padding:1px 6px">Cookies</span>' : '') +
                        '</div>' +
                        '<button class="btn-admin danger" onclick="window.adminDeleteCred(' + c.id + ')">Remove</button>' +
                        '</div>';
                });
            }

            html += '<div style="margin-top:16px"><div class="info-label" style="margin-bottom:8px">ADD CREDENTIAL</div>' +
                '<div class="config-grid">' +
                '<div class="config-group"><label>Site Name</label><input type="text" id="credSite" placeholder="e.g. linkedin"></div>' +
                '<div class="config-group"><label>Username</label><input type="text" id="credUser" placeholder="email@example.com"></div>' +
                '<div class="config-group"><label>Password</label><input type="password" id="credPass" placeholder="password"></div>' +
                '</div>' +
                '<div class="admin-actions"><button class="btn-admin primary" onclick="window.adminAddCred()">Add Credential</button></div></div>';

            document.getElementById('credentialsContent').innerHTML = html;
        });
    }
    window.adminAddCred = function () {
        var site = document.getElementById('credSite').value.trim();
        var user = document.getElementById('credUser').value.trim();
        var pass = document.getElementById('credPass').value;
        if (!site || !user || !pass) { BC.showToast('All fields required', 'error'); return; }
        BC.api('/api/admin/credentials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ site_name: site, username: user, password: pass })
        }).then(function () {
            BC.showToast('Credential added', 'success');
            loadCredentials();
        });
    };
    window.adminDeleteCred = function (id) {
        BC.api('/api/admin/credentials/' + id, { method: 'DELETE' }).then(function () {
            BC.showToast('Credential removed', 'success');
            loadCredentials();
        });
    };

    // ── 10. Scheduler ──
    function loadScheduler() {
        BC.api('/api/admin/scheduler').then(function (d) {
            var ps = d.pipeline_state || {};
            var sched = d.schedule || {};
            var html = '<div class="info-grid">';

            ['discovery', 'matching', 'application'].forEach(function (key) {
                var state = ps[key] || {};
                var s = sched[key] || {};
                var status = state.status || 'idle';
                var pillClass = status === 'running' ? 'ok' : (status === 'error' ? 'fail' : 'warn');
                var interval = s.interval_hours ? s.interval_hours + 'h' : (s.interval_minutes ? s.interval_minutes + 'm' : '-');
                html += infoItem(
                    BC.capitalize(key),
                    '<span class="status-pill ' + pillClass + '" style="margin-right:8px">' + E(status) + '</span> Interval: ' + interval
                );
            });

            html += '</div>';
            if (d.note) {
                html += '<div style="padding-top:12px;font-size:0.75rem;color:var(--text-dim)">' + E(d.note) + '</div>';
            }
            document.getElementById('schedulerContent').innerHTML = html;
        });
    }

    // ── Init ──
    restoreCollapse();
    loadSystemHealth();
    loadUserInfo();
    loadApiKeys();
    loadDiscovery();
    loadLogs();
    loadConfig();
    loadAnalytics();
    loadDatabase();
    loadCredentials();
    loadScheduler();

})();
