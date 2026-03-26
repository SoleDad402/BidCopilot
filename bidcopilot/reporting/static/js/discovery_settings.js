/**
 * BidCopilot — Discovery Settings Page JS
 */
(function () {
    'use strict';

    var E = BC.esc;
    var configData = null;
    var isDirty = false;

    var SENIORITY_OPTIONS = ['junior', 'mid', 'senior', 'staff', 'lead', 'principal', 'director', 'vp'];
    var JOB_TYPE_OPTIONS = ['full-time', 'contract', 'part-time', 'internship', 'freelance'];
    var REMOTE_OPTIONS = ['remote_only', 'hybrid', 'onsite', 'any'];

    // ── Section toggle ──
    function toggleSection(header) {
        var card = header.closest('.section-card');
        var id = card.dataset.section;
        card.classList.toggle('collapsed');
        var state = JSON.parse(localStorage.getItem('bc_disc_collapsed') || '{}');
        state[id] = card.classList.contains('collapsed');
        localStorage.setItem('bc_disc_collapsed', JSON.stringify(state));
    }
    window.toggleSection = toggleSection;

    function restoreCollapse() {
        var state = JSON.parse(localStorage.getItem('bc_disc_collapsed') || '{}');
        Object.keys(state).forEach(function (id) {
            if (state[id]) {
                var card = document.querySelector('.section-card[data-section="' + id + '"]');
                if (card) card.classList.add('collapsed');
            }
        });
    }

    function markDirty() {
        if (!isDirty) {
            isDirty = true;
            document.getElementById('unsavedIndicator').classList.add('visible');
        }
    }

    function markClean() {
        isDirty = false;
        document.getElementById('unsavedIndicator').classList.remove('visible');
    }

    // ── Tag input helper ──
    function tagInputHtml(id, items, placeholder) {
        var html = '<div class="tag-input-container" id="' + id + 'Container">';
        (items || []).forEach(function (val, idx) {
            html += '<span class="tag-pill">' + E(val) +
                '<button class="tag-remove" onclick="window.discoveryRemoveTag(\'' + id + '\',' + idx + ')">&times;</button></span>';
        });
        html += '<input type="text" class="tag-input-field" placeholder="' + E(placeholder) + '" onkeydown="window.discoveryAddTag(event,\'' + id + '\')">';
        html += '</div>';
        return html;
    }

    // ── Chip selector ──
    function chipGridHtml(id, options, selected) {
        var html = '<div class="chip-grid" id="' + id + '">';
        options.forEach(function (opt) {
            var active = (selected || []).indexOf(opt) !== -1;
            html += '<span class="chip' + (active ? ' active' : '') + '" onclick="window.discoveryToggleChip(this,\'' + id + '\')">' + E(opt) + '</span>';
        });
        html += '</div>';
        return html;
    }

    // ── Load config ──
    function loadConfig() {
        BC.api('/api/discovery-config').then(function (data) {
            configData = data;
            renderGlobalSettings(data.global_settings);
            renderAdapterSettings(data.adapters, data.adapter_metadata);
        });
    }

    // ── Render global settings ──
    function renderGlobalSettings(g) {
        var html = '<div class="form-grid">';

        // Keywords
        html += '<div class="form-group full-width">' +
            '<label class="form-label">Search Keywords (empty = auto from profile)</label>' +
            tagInputHtml('globalKeywords', g.keywords || [], 'Type keyword and press Enter...') +
            '</div>';

        // Seniority levels
        html += '<div class="form-group full-width">' +
            '<label class="form-label">Seniority Levels</label>' +
            chipGridHtml('globalSeniority', SENIORITY_OPTIONS, g.seniority_levels || []) +
            '</div>';

        // Job types
        html += '<div class="form-group full-width">' +
            '<label class="form-label">Job Types</label>' +
            chipGridHtml('globalJobTypes', JOB_TYPE_OPTIONS, g.job_types || []) +
            '</div>';

        // Remote preference
        html += '<div class="form-group">' +
            '<label class="form-label">Remote Preference</label>' +
            '<select class="form-select" id="globalRemote" onchange="markDirty()">';
        REMOTE_OPTIONS.forEach(function (opt) {
            html += '<option value="' + opt + '"' + (g.remote_preference === opt ? ' selected' : '') + '>' + E(opt.replace('_', ' ')) + '</option>';
        });
        html += '</select></div>';

        // Numeric settings
        html += '<div class="form-group"><label class="form-label">Salary Floor</label>' +
            '<input type="number" class="form-input" id="globalSalaryFloor" value="' + (g.salary_floor || '') + '" placeholder="e.g. 80000" oninput="markDirty()"></div>';

        html += '<div class="form-group"><label class="form-label">Posted Within (days)</label>' +
            '<input type="number" class="form-input" id="globalPostedDays" value="' + (g.posted_within_days || 7) + '" oninput="markDirty()"></div>';

        html += '<div class="form-group"><label class="form-label">Max Results / Adapter</label>' +
            '<input type="number" class="form-input" id="globalMaxResults" value="' + (g.max_results_per_adapter || 100) + '" oninput="markDirty()"></div>';

        html += '<div class="form-group"><label class="form-label">Max Pages (default)</label>' +
            '<input type="number" class="form-input" id="globalMaxPages" value="' + (g.max_pages_default || 5) + '" oninput="markDirty()"></div>';

        // Excluded companies
        html += '<div class="form-group full-width">' +
            '<label class="form-label">Excluded Companies</label>' +
            tagInputHtml('globalExcluded', g.excluded_companies || [], 'Type company name and press Enter...') +
            '</div>';

        // Experience range
        html += '<div class="form-group"><label class="form-label">Min Years Experience</label>' +
            '<input type="number" class="form-input" id="globalExpMin" value="' + (g.experience_years_min || '') + '" placeholder="Any" oninput="markDirty()"></div>';
        html += '<div class="form-group"><label class="form-label">Max Years Experience</label>' +
            '<input type="number" class="form-input" id="globalExpMax" value="' + (g.experience_years_max || '') + '" placeholder="Any" oninput="markDirty()"></div>';

        html += '</div>';
        document.getElementById('globalSettingsContent').innerHTML = html;
    }

    // ── Render per-adapter settings ──
    function renderAdapterSettings(adapterOverrides, metadata) {
        var html = '';
        var names = Object.keys(metadata).sort();

        names.forEach(function (name) {
            var meta = metadata[name];
            var override = adapterOverrides[name] || {};
            var hasCats = meta.supported_categories && meta.supported_categories.length > 0;
            var currentCats = override.categories || meta.default_categories || [];

            html += '<div class="adapter-config-card" data-adapter="' + E(name) + '">';
            html += '<div class="adapter-config-header">';
            html += '<div class="adapter-config-name">' + E(name) + '</div>';
            html += '<div style="display:flex;gap:6px">';
            if (meta.requires_auth) html += '<span class="adapter-config-badge auth">Auth Required</span>';
            html += '<span class="adapter-config-badge ' + (meta.enabled ? 'enabled' : 'disabled') + '">' + (meta.enabled ? 'Enabled' : 'Disabled') + '</span>';
            html += '</div></div>';

            if (hasCats) {
                html += '<div style="margin-bottom:10px"><label class="form-label">Categories</label>';
                html += '<div class="checkbox-grid">';
                meta.supported_categories.forEach(function (cat) {
                    var checked = currentCats.indexOf(cat) !== -1;
                    html += '<label class="checkbox-label' + (checked ? ' checked' : '') + '">' +
                        '<input type="checkbox" value="' + E(cat) + '"' + (checked ? ' checked' : '') +
                        ' onchange="window.discoveryToggleCat(this)" data-adapter="' + E(name) + '">' +
                        E(cat) + '</label>';
                });
                html += '</div></div>';
            }

            // Custom keywords
            html += '<div style="margin-bottom:10px"><label class="form-label">Custom Keywords (overrides global)</label>';
            html += tagInputHtml('kw_' + name, override.keywords || [], 'Leave empty to use global keywords');
            html += '</div>';

            // Max pages
            html += '<div style="display:flex;gap:12px;margin-bottom:10px">';
            html += '<div><label class="form-label">Max Pages</label>' +
                '<input type="number" class="form-input" style="width:80px" data-adapter="' + E(name) + '" data-field="max_pages" value="' + (override.max_pages || '') + '" placeholder="global" oninput="markDirty()"></div>';
            html += '<div><label class="form-label">Max Results</label>' +
                '<input type="number" class="form-input" style="width:80px" data-adapter="' + E(name) + '" data-field="max_results" value="' + (override.max_results || '') + '" placeholder="global" oninput="markDirty()"></div>';
            html += '</div>';

            // ── Rich filters (Jobright-style) ──
            var hasRichFilters = (meta.supported_work_models && meta.supported_work_models.length > 0) ||
                                 (meta.supported_seniority && meta.supported_seniority.length > 0);

            if (hasRichFilters) {
                html += '<div style="border-top:1px solid var(--border-subtle);margin-top:12px;padding-top:12px">';
                html += '<div style="font-size:0.75rem;font-weight:600;color:var(--accent);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px">Advanced Filters</div>';

                // Work Model
                if (meta.supported_work_models && meta.supported_work_models.length > 0) {
                    var currentWM = override.work_models || [];
                    html += '<div style="margin-bottom:10px"><label class="form-label">Work Model</label><div class="chip-grid" id="wm_' + name + '">';
                    meta.supported_work_models.forEach(function (wm) {
                        var active = currentWM.indexOf(wm) !== -1;
                        html += '<span class="chip' + (active ? ' active' : '') + '" onclick="window.discoveryToggleChip(this,\'wm_' + name + '\')">' + E(wm) + '</span>';
                    });
                    html += '</div></div>';
                }

                // Seniority (adapter-specific, may differ from global)
                if (meta.supported_seniority && meta.supported_seniority.length > 0) {
                    html += '<div style="margin-bottom:10px"><label class="form-label">Experience Level</label><div class="chip-grid" id="sen_' + name + '">';
                    meta.supported_seniority.forEach(function (s) {
                        html += '<span class="chip" onclick="window.discoveryToggleChip(this,\'sen_' + name + '\')">' + E(s.replace(/_/g, ' ')) + '</span>';
                    });
                    html += '</div></div>';
                }

                // Company Stage
                if (meta.supported_company_stages && meta.supported_company_stages.length > 0) {
                    var currentCS = override.company_stages || [];
                    html += '<div style="margin-bottom:10px"><label class="form-label">Company Stage</label><div class="chip-grid" id="cs_' + name + '">';
                    meta.supported_company_stages.forEach(function (cs) {
                        var active = currentCS.indexOf(cs) !== -1;
                        html += '<span class="chip' + (active ? ' active' : '') + '" onclick="window.discoveryToggleChip(this,\'cs_' + name + '\')">' + E(cs) + '</span>';
                    });
                    html += '</div></div>';
                }

                // Role Type
                if (meta.supported_role_types && meta.supported_role_types.length > 0) {
                    var currentRT = override.role_type || '';
                    html += '<div style="margin-bottom:10px"><label class="form-label">Role Type</label><div class="chip-grid" id="rt_' + name + '">';
                    meta.supported_role_types.forEach(function (rt) {
                        var active = currentRT === rt;
                        html += '<span class="chip' + (active ? ' active' : '') + '" onclick="window.discoverySelectOne(this,\'rt_' + name + '\')">' + E(rt) + '</span>';
                    });
                    html += '</div></div>';
                }

                // Industries
                html += '<div style="margin-bottom:10px"><label class="form-label">Industries</label>';
                html += tagInputHtml('ind_' + name, override.industries || [], 'e.g. Information Technology, AI, Software...');
                html += '</div>';

                // Skills filter
                html += '<div style="margin-bottom:10px"><label class="form-label">Required Skills</label>';
                html += tagInputHtml('sk_' + name, override.skills || [], 'e.g. JavaScript, Python, AWS...');
                html += '</div>';

                // Toggle options
                html += '<div style="display:flex;flex-wrap:wrap;gap:16px;margin-top:8px">';
                html += '<label style="display:flex;align-items:center;gap:6px;font-size:0.8125rem;color:var(--text-secondary);cursor:pointer">' +
                    '<input type="checkbox" data-adapter="' + E(name) + '" data-field="h1b_only"' + (override.h1b_only ? ' checked' : '') + ' onchange="markDirty()" style="accent-color:var(--accent)"> H1B Sponsorship Only</label>';
                html += '<label style="display:flex;align-items:center;gap:6px;font-size:0.8125rem;color:var(--text-secondary);cursor:pointer">' +
                    '<input type="checkbox" data-adapter="' + E(name) + '" data-field="exclude_staffing_agency"' + (override.exclude_staffing_agency ? ' checked' : '') + ' onchange="markDirty()" style="accent-color:var(--accent)"> Exclude Staffing Agencies</label>';
                html += '</div>';

                html += '</div>';
            }

            html += '</div>';
        });

        document.getElementById('adapterSettingsContent').innerHTML = html;
    }

    // ── Tag operations ──
    window.discoveryAddTag = function (event, id) {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        var input = event.target;
        var val = input.value.trim();
        if (!val) return;

        var container = document.getElementById(id + 'Container');
        var pills = container.querySelectorAll('.tag-pill');
        // Check for duplicates
        for (var i = 0; i < pills.length; i++) {
            if (pills[i].textContent.replace('\u00d7', '').trim() === val) return;
        }

        var pill = document.createElement('span');
        pill.className = 'tag-pill';
        pill.innerHTML = E(val) + '<button class="tag-remove" onclick="this.parentElement.remove();markDirty()">&times;</button>';
        container.insertBefore(pill, input);
        input.value = '';
        markDirty();
    };

    window.discoveryRemoveTag = function (id, idx) {
        var container = document.getElementById(id + 'Container');
        var pills = container.querySelectorAll('.tag-pill');
        if (pills[idx]) { pills[idx].remove(); markDirty(); }
    };

    window.discoveryToggleChip = function (el, groupId) {
        el.classList.toggle('active');
        markDirty();
    };

    window.discoveryToggleCat = function (cb) {
        cb.parentElement.classList.toggle('checked', cb.checked);
        markDirty();
    };

    // Single-select chip (radio-like)
    window.discoverySelectOne = function (el, groupId) {
        var group = document.getElementById(groupId);
        if (!group) return;
        var wasActive = el.classList.contains('active');
        group.querySelectorAll('.chip').forEach(function (c) { c.classList.remove('active'); });
        if (!wasActive) el.classList.add('active');
        markDirty();
    };

    // ── Collect tags from container ──
    function collectTags(containerId) {
        var container = document.getElementById(containerId + 'Container');
        if (!container) return [];
        var pills = container.querySelectorAll('.tag-pill');
        var result = [];
        pills.forEach(function (p) {
            var text = p.textContent.replace('\u00d7', '').trim();
            if (text) result.push(text);
        });
        return result;
    }

    // ── Collect chips from group ──
    function collectChips(groupId) {
        var el = document.getElementById(groupId);
        if (!el) return [];
        var result = [];
        el.querySelectorAll('.chip.active').forEach(function (c) {
            result.push(c.textContent.trim());
        });
        return result;
    }

    // ── Save ──
    window.discoverySave = function () {
        var btn = document.getElementById('saveBtn');
        btn.textContent = 'Saving...';
        btn.disabled = true;

        // Collect global settings
        var globalSettings = {
            keywords: collectTags('globalKeywords'),
            seniority_levels: collectChips('globalSeniority'),
            job_types: collectChips('globalJobTypes'),
            remote_preference: document.getElementById('globalRemote').value,
            salary_floor: Number(document.getElementById('globalSalaryFloor').value) || null,
            posted_within_days: Number(document.getElementById('globalPostedDays').value) || 7,
            max_results_per_adapter: Number(document.getElementById('globalMaxResults').value) || 100,
            max_pages_default: Number(document.getElementById('globalMaxPages').value) || 5,
            excluded_companies: collectTags('globalExcluded'),
            experience_years_min: Number(document.getElementById('globalExpMin').value) || null,
            experience_years_max: Number(document.getElementById('globalExpMax').value) || null,
        };

        // Collect per-adapter settings
        var adapters = {};
        document.querySelectorAll('.adapter-config-card').forEach(function (card) {
            var name = card.dataset.adapter;
            var settings = {};

            // Categories
            var catChecks = card.querySelectorAll('.checkbox-grid input:checked');
            if (catChecks.length > 0) {
                settings.categories = [];
                catChecks.forEach(function (cb) { settings.categories.push(cb.value); });
            }

            // Custom keywords
            var kw = collectTags('kw_' + name);
            if (kw.length > 0) settings.keywords = kw;

            // Max pages / max results
            var mpInput = card.querySelector('[data-field="max_pages"]');
            var mrInput = card.querySelector('[data-field="max_results"]');
            if (mpInput && mpInput.value) settings.max_pages = Number(mpInput.value);
            if (mrInput && mrInput.value) settings.max_results = Number(mrInput.value);

            // Rich filters (work models, company stages, role type, industries, skills, toggles)
            var wmChips = collectChips('wm_' + name);
            if (wmChips.length > 0) settings.work_models = wmChips;
            var csChips = collectChips('cs_' + name);
            if (csChips.length > 0) settings.company_stages = csChips;
            var rtChips = collectChips('rt_' + name);
            if (rtChips.length > 0) settings.role_type = rtChips[0];
            var industries = collectTags('ind_' + name);
            if (industries.length > 0) settings.industries = industries;
            var skills = collectTags('sk_' + name);
            if (skills.length > 0) settings.skills = skills;

            var h1bCb = card.querySelector('[data-field="h1b_only"]');
            if (h1bCb && h1bCb.checked) settings.h1b_only = true;
            var staffCb = card.querySelector('[data-field="exclude_staffing_agency"]');
            if (staffCb && staffCb.checked) settings.exclude_staffing_agency = true;

            if (Object.keys(settings).length > 0) {
                adapters[name] = settings;
            }
        });

        var payload = { global_settings: globalSettings, adapters: adapters };

        BC.api('/api/discovery-config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function () {
            markClean();
            BC.showToast('Discovery settings saved', 'success');
        }).catch(function () {
            BC.showToast('Failed to save settings', 'error');
        }).finally(function () {
            btn.textContent = 'Save Settings';
            btn.disabled = false;
        });
    };

    // Make markDirty available globally for inline onchange/oninput
    window.markDirty = markDirty;

    // ── Keyboard shortcut ──
    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            if (isDirty) window.discoverySave();
        }
    });

    // ── Save bar portal (move to body to escape #page-content transform) ──
    function mountSaveBar() {
        var source = document.getElementById('discoverySaveBarSource');
        if (!source) return;
        var bar = document.getElementById('discoverySaveBar');
        if (bar) {
            document.body.appendChild(bar);
            bar.style.display = '';
        }
    }

    function unmountSaveBar() {
        var bar = document.getElementById('discoverySaveBar');
        if (bar && bar.parentElement === document.body) {
            bar.remove();
        }
    }

    // Clean up on SPA navigation
    window.addEventListener('beforeunload', unmountSaveBar);
    // Also clean up when router navigates away
    var _origPushState = history.pushState;
    history.pushState = function () {
        unmountSaveBar();
        return _origPushState.apply(this, arguments);
    };
    window.addEventListener('popstate', unmountSaveBar);

    // ── Init ──
    restoreCollapse();
    mountSaveBar();
    loadConfig();

})();
