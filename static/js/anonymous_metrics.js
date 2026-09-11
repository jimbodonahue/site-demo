/**
 * First-party anonymous usage metrics.
 * Only active when the visitor has accepted cookie/consent preferences.
 * Never sends notebook source, names, emails, or other personal data.
 */
(function (window, document) {
    const STORAGE_ID_KEY = 'anon_metrics_id';
    const CONSENT_KEY = 'gdpr_consent';
    const HEARTBEAT_MS = 15000;
    const FLUSH_MS = 20000;
    const MAX_QUEUE = 30;

    let queue = [];
    let flushTimer = null;
    let heartbeatTimer = null;
    let pageStartedAt = Date.now();
    let activeMs = 0;
    let lastActiveTick = Date.now();
    let isVisible = !document.hidden;
    let pageContext = {
        path: window.location.pathname,
        exerciseSlug: '',
    };

    function hasConsent() {
        return localStorage.getItem(CONSENT_KEY) === 'accepted';
    }

    function getAnonymousId() {
        let id = localStorage.getItem(STORAGE_ID_KEY);
        if (!id) {
            if (window.crypto && typeof window.crypto.randomUUID === 'function') {
                id = window.crypto.randomUUID();
            } else {
                id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
                    const rand = (Math.random() * 16) | 0;
                    const value = char === 'x' ? rand : (rand & 0x3) | 0x8;
                    return value.toString(16);
                });
            }
            localStorage.setItem(STORAGE_ID_KEY, id);
        }
        return id;
    }

    function csrfToken() {
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        if (match) {
            return decodeURIComponent(match[1]);
        }
        return document.querySelector('input[name=csrfmiddlewaretoken]')?.value || '';
    }

    function accumulateActiveTime() {
        if (!isVisible) {
            return;
        }
        const now = Date.now();
        activeMs += Math.max(0, now - lastActiveTick);
        lastActiveTick = now;
    }

    function enqueue(eventType, properties) {
        if (!hasConsent() || !window.ANON_METRICS_URL) {
            return;
        }
        accumulateActiveTime();
        queue.push({
            event_type: eventType,
            path: pageContext.path,
            exercise_slug: pageContext.exerciseSlug || '',
            properties: Object.assign({ active_ms: activeMs }, properties || {}),
        });
        if (queue.length >= MAX_QUEUE) {
            flush(false);
        } else {
            scheduleFlush();
        }
    }

    function scheduleFlush() {
        if (flushTimer) {
            return;
        }
        flushTimer = window.setTimeout(() => {
            flushTimer = null;
            flush(false);
        }, FLUSH_MS);
    }

    function flush(useBeacon) {
        if (!hasConsent() || !queue.length || !window.ANON_METRICS_URL) {
            queue = [];
            return;
        }
        const events = queue.splice(0, MAX_QUEUE);
        const body = JSON.stringify({
            anonymous_id: getAnonymousId(),
            events,
        });

        if (useBeacon && navigator.sendBeacon) {
            const blob = new Blob([body], { type: 'application/json' });
            navigator.sendBeacon(window.ANON_METRICS_URL, blob);
            return;
        }

        fetch(window.ANON_METRICS_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken(),
            },
            body,
            credentials: 'same-origin',
            keepalive: true,
        }).catch(() => {
            // Drop failed batches quietly; metrics must not break the UI.
        });
    }

    function startHeartbeat() {
        stopHeartbeat();
        heartbeatTimer = window.setInterval(() => {
            if (!hasConsent()) {
                return;
            }
            accumulateActiveTime();
            enqueue('heartbeat', { active_ms: activeMs });
        }, HEARTBEAT_MS);
    }

    function stopHeartbeat() {
        if (heartbeatTimer) {
            window.clearInterval(heartbeatTimer);
            heartbeatTimer = null;
        }
    }

    function onVisibilityChange() {
        if (document.hidden) {
            accumulateActiveTime();
            isVisible = false;
            enqueue('heartbeat', { active_ms: activeMs, reason: 'hidden' });
            flush(true);
        } else {
            isVisible = true;
            lastActiveTick = Date.now();
        }
    }

    function onPageLeave() {
        accumulateActiveTime();
        enqueue('page_leave', {
            active_ms: activeMs,
            duration_ms: Date.now() - pageStartedAt,
        });
        flush(true);
    }

    function init(options) {
        pageContext = {
            path: (options && options.path) || window.location.pathname,
            exerciseSlug: (options && options.exerciseSlug) || '',
        };
        pageStartedAt = Date.now();
        activeMs = 0;
        lastActiveTick = Date.now();

        if (!hasConsent()) {
            return;
        }

        enqueue('page_view', { title: document.title.slice(0, 120) });
        startHeartbeat();
    }

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', onPageLeave);

    window.AnonymousMetrics = {
        init,
        track(eventType, properties) {
            enqueue(eventType, properties);
        },
        trackCodeRun(properties) {
            enqueue('code_run', properties);
        },
        trackReset(properties) {
            enqueue('code_reset', properties);
        },
        trackEvaluate(properties) {
            enqueue('evaluate', properties);
        },
        trackFeatureSelect(properties) {
            enqueue('feature_select', properties);
        },
        flush,
        hasConsent,
    };

    // Auto-init for ordinary pages; exercise pages may re-init with slug context.
    window.addEventListener('DOMContentLoaded', () => {
        if (!window.AnonymousMetrics._booted) {
            window.AnonymousMetrics._booted = true;
            init({});
        }
    });
})(window, document);
