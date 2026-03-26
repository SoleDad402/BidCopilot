/**
 * BidCopilot — Client-Side Router
 * SPA-like navigation: header persists, only page content swaps.
 * Intercepts [data-nav] link clicks, fetches target page,
 * extracts #page-content + #page-script + #page-styles, swaps them in.
 */
(function () {
    'use strict';

    var isNavigating = false;
    var pageCache = {};

    /* ── Route map for nav highlighting ── */
    var NAV_MAP = {
        '/': 'dashboard',
        '/profile': 'profile',
        '/monitor': 'monitor',
        '/admin': 'admin'
    };

    /* ── Intercept nav link clicks ── */
    document.addEventListener('click', function (e) {
        var link = e.target.closest('[data-nav]');
        if (!link) return;

        var href = link.getAttribute('href');
        if (!href || href === window.location.pathname) {
            e.preventDefault();
            return;
        }

        // Only handle internal links
        if (href.startsWith('http') && !href.startsWith(window.location.origin)) return;

        e.preventDefault();
        navigateTo(href);
    });

    /* ── Handle browser back/forward ── */
    window.addEventListener('popstate', function () {
        navigateTo(window.location.pathname, true);
    });

    /* ── Core navigation ── */
    function navigateTo(url, isPopState) {
        if (isNavigating) return;
        isNavigating = true;

        var content = document.getElementById('page-content');

        // Fade out current content
        content.style.transition = 'opacity 0.15s ease, transform 0.15s ease';
        content.style.opacity = '0';
        content.style.transform = 'translateY(4px)';

        // Update nav active state immediately
        updateNav(url);

        // Fetch or use cache
        var fetchPromise = pageCache[url]
            ? Promise.resolve(pageCache[url])
            : fetch(url).then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.text();
            }).then(function (html) {
                pageCache[url] = html;
                return html;
            });

        // Wait for fade out + fetch
        setTimeout(function () {
            fetchPromise.then(function (html) {
                swapContent(html, url);
                if (!isPopState) {
                    window.history.pushState(null, '', url);
                }
                // Update title
                var titleMatch = html.match(/<title>([^<]*)<\/title>/);
                if (titleMatch) document.title = titleMatch[1];
            }).catch(function (err) {
                // On 401, redirect to login instead of hard nav
                if (err.message && err.message.indexOf('401') !== -1) {
                    window.location.href = '/login';
                    return;
                }
                // Fallback: hard navigation
                console.warn('Router fallback:', err);
                window.location.href = url;
            }).then(function () {
                isNavigating = false;
            });
        }, 150);
    }

    /* ── Swap page content ── */
    function swapContent(html, url) {
        var parser = new DOMParser();
        var doc = parser.parseFromString(html, 'text/html');

        // Swap page-specific CSS
        var newStyles = doc.getElementById('page-styles');
        var currentStyles = document.getElementById('page-styles');
        if (newStyles && currentStyles) {
            currentStyles.textContent = newStyles.textContent;
        }

        // Swap page content
        var newContent = doc.getElementById('page-content');
        var currentContent = document.getElementById('page-content');
        if (newContent && currentContent) {
            currentContent.innerHTML = newContent.innerHTML;
        }

        // Swap and execute page scripts
        var newScript = doc.getElementById('page-script');
        var currentScript = document.getElementById('page-script');
        if (newScript && currentScript) {
            currentScript.innerHTML = '';
            // Extract script tags and execute them
            var scripts = newScript.querySelectorAll('script');
            if (scripts.length > 0) {
                scripts.forEach(function (oldScript) {
                    var newScriptEl = document.createElement('script');
                    if (oldScript.src) {
                        newScriptEl.src = oldScript.src;
                    } else {
                        newScriptEl.textContent = oldScript.textContent;
                    }
                    currentScript.appendChild(newScriptEl);
                });
            } else if (newScript.textContent.trim()) {
                // Script content directly in the div (no script tag wrapper from Jinja)
                var inlineScript = document.createElement('script');
                inlineScript.textContent = newScript.textContent;
                currentScript.appendChild(inlineScript);
            }
        }

        // Fade in
        requestAnimationFrame(function () {
            currentContent.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
            currentContent.style.opacity = '1';
            currentContent.style.transform = 'translateY(0)';
        });

        // Scroll to top
        window.scrollTo({ top: 0, behavior: 'instant' });
    }

    /* ── Update nav active state ── */
    function updateNav(url) {
        var nav = document.getElementById('mainNav');
        if (!nav) return;
        var links = nav.querySelectorAll('a[data-nav]');
        links.forEach(function (link) {
            var href = link.getAttribute('href');
            if (href === url || (url === '/' && href === '/')) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    /* ── Invalidate cache (called after mutations) ── */
    window.BCRouter = {
        invalidate: function (url) {
            if (url) {
                delete pageCache[url];
            } else {
                pageCache = {};
            }
        }
    };
})();
