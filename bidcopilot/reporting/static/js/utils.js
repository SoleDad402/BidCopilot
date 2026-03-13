/**
 * BidCopilot — Shared JS Utilities
 * Toast notifications, API helper, formatters, animated counters
 */
(function () {
    'use strict';

    /* ── HTML Escape ── */
    var _escDiv = document.createElement('div');
    function esc(s) {
        if (s == null) return '';
        _escDiv.textContent = String(s);
        return _escDiv.innerHTML;
    }

    /* ── Capitalize ── */
    function capitalize(s) {
        return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
    }

    /* ── Time Ago ── */
    function timeAgo(iso) {
        if (!iso) return '';
        var diff = (Date.now() - new Date(iso).getTime()) / 1000;
        if (diff < 0) return 'just now';
        if (diff < 60) return Math.floor(diff) + 's ago';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
        return Math.floor(diff / 604800) + 'w ago';
    }

    /* ── Toast Notifications ── */
    function showToast(msg, type) {
        type = type || 'info';
        var container = document.getElementById('toasts');
        if (!container) return;
        var el = document.createElement('div');
        el.className = 'toast ' + type;
        el.innerHTML = '<span class="toast-dot"></span>' + esc(msg);
        container.appendChild(el);
        setTimeout(function () {
            el.classList.add('removing');
            setTimeout(function () { el.remove(); }, 200);
        }, 3500);
    }

    /* ── API Helper ── */
    function api(url, opts) {
        opts = opts || {};
        return fetch(url, opts).then(function (res) {
            if (!res.ok) throw new Error('HTTP ' + res.status);
            return res.json();
        }).catch(function (e) {
            showToast('Request failed: ' + e.message, 'error');
            throw e;
        });
    }

    /* ── Animated Number Counter ── */
    function animateValue(el, newVal) {
        var startVal = parseInt(el.getAttribute('data-value')) || 0;
        newVal = parseInt(newVal) || 0;
        if (startVal === newVal) {
            el.textContent = newVal;
            return;
        }
        el.setAttribute('data-value', newVal);
        var duration = 500;
        var startTime = null;
        var diff = newVal - startVal;

        function step(ts) {
            if (!startTime) startTime = ts;
            var progress = Math.min((ts - startTime) / duration, 1);
            var eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
            var current = Math.round(startVal + diff * eased);
            el.textContent = current;
            if (progress < 1) {
                requestAnimationFrame(step);
            } else {
                el.textContent = newVal;
            }
        }
        requestAnimationFrame(step);
    }

    /* ── Skeleton Generators ── */
    function tableSkeletonRows(cols, rows) {
        var html = '';
        for (var r = 0; r < rows; r++) {
            html += '<tr>';
            for (var c = 0; c < cols; c++) {
                var w = c === 0 ? 'w-3\\/4' : (c === cols - 1 ? 'w-16' : 'w-1\\/2');
                html += '<td><div class="skeleton skeleton-block ' + w + '" style="height:12px"></div></td>';
            }
            html += '</tr>';
        }
        return html;
    }

    function queueSkeletonCards(count) {
        var html = '';
        for (var i = 0; i < count; i++) {
            html += '<div class="skeleton-card">' +
                '<div class="skeleton skeleton-block w-3\\/4" style="height:13px;margin-bottom:6px"></div>' +
                '<div class="skeleton skeleton-block w-1\\/2" style="height:10px;margin-bottom:8px"></div>' +
                '<div style="display:flex;gap:6px">' +
                '<div class="skeleton skeleton-block w-16" style="height:10px"></div>' +
                '<div class="skeleton skeleton-block w-10" style="height:10px"></div>' +
                '</div></div>';
        }
        return html;
    }

    function activitySkeletonItems(count) {
        var html = '<div class="timeline">';
        for (var i = 0; i < count; i++) {
            html += '<div class="timeline-item" style="padding:8px 0">' +
                '<div class="skeleton" style="width:11px;height:11px;border-radius:50%;flex-shrink:0;margin-top:4px"></div>' +
                '<div style="flex:1">' +
                '<div class="skeleton skeleton-block w-3\\/4" style="height:12px;margin-bottom:5px"></div>' +
                '<div class="skeleton skeleton-block w-1\\/4" style="height:9px"></div>' +
                '</div></div>';
        }
        html += '</div>';
        return html;
    }

    /* ── Pagination Helper ── */
    function showPagination(elId, page, pages, callback) {
        var el = document.getElementById(elId);
        if (!pages || pages <= 1) {
            el.style.display = 'none';
            el.innerHTML = '';
            return;
        }
        el.style.display = 'flex';
        el.innerHTML =
            '<button ' + (page <= 1 ? 'disabled' : '') + '>Prev</button>' +
            '<span class="page-info">Page ' + page + ' of ' + pages + '</span>' +
            '<button ' + (page >= pages ? 'disabled' : '') + '>Next</button>';
        var buttons = el.querySelectorAll('button');
        buttons[0].onclick = function () { if (page > 1) callback(page - 1); };
        buttons[1].onclick = function () { if (page < pages) callback(page + 1); };
    }

    function hidePagination(elId) {
        var el = document.getElementById(elId);
        if (el) {
            el.style.display = 'none';
            el.innerHTML = '';
        }
    }

    /* ── Nested value helpers (for profile form) ── */
    function getNestedValue(obj, path) {
        return path.split('.').reduce(function (o, k) {
            return (o && o[k] !== undefined) ? o[k] : undefined;
        }, obj);
    }

    function setNestedValue(obj, path, value) {
        var keys = path.split('.');
        var current = obj;
        for (var i = 0; i < keys.length - 1; i++) {
            if (!current[keys[i]] || typeof current[keys[i]] !== 'object') {
                current[keys[i]] = {};
            }
            current = current[keys[i]];
        }
        current[keys[keys.length - 1]] = value;
    }

    /* ── Export to global namespace ── */
    window.BC = {
        esc: esc,
        capitalize: capitalize,
        timeAgo: timeAgo,
        showToast: showToast,
        api: api,
        animateValue: animateValue,
        tableSkeletonRows: tableSkeletonRows,
        queueSkeletonCards: queueSkeletonCards,
        activitySkeletonItems: activitySkeletonItems,
        showPagination: showPagination,
        hidePagination: hidePagination,
        getNestedValue: getNestedValue,
        setNestedValue: setNestedValue
    };

    // Also expose showToast directly for convenience
    window.showToast = showToast;
})();
