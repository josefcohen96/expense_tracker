// קריאה לזירה: the push card on the workouts #profile view (templates/pages/workout.html).
// Server side: api/push.py (/api/workouts/push/*) and services/push_service.py.
(function () {
    'use strict';

    var card = document.querySelector('[data-arena-push]');
    if (!card) return;
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return;

    var API = '/api/workouts/push';
    var sub = card.querySelector('[data-push-sub]');
    var btnOn = card.querySelector('[data-push-on]');
    var btnTest = card.querySelector('[data-push-test]');
    var btnOff = card.querySelector('[data-push-off]');
    var publicKey = null;
    var busy = false;

    function toast(msg, actionLabel, onAction) {
        if (window.AppToast) window.AppToast(msg, actionLabel, onAction, actionLabel ? 5000 : undefined);
    }

    function fail(err) {
        console.error('[arena-push]', err);
        toast('לא הצלחנו להפעיל התראות');
    }

    function isIos() {
        return /iphone|ipad|ipod/i.test(navigator.userAgent) ||
            (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    }

    function isStandalone() {
        return navigator.standalone === true ||
            (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches);
    }

    // base64url VAPID key -> the Uint8Array applicationServerKey takes
    function keyBytes(b64) {
        var padded = (b64 + '===='.slice((b64.length + 3) % 4)).replace(/-/g, '+').replace(/_/g, '/');
        var raw = atob(padded);
        var out = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
        return out;
    }

    function api(method, path, body) {
        return fetch(API + path, {
            method: method,
            credentials: 'same-origin',
            headers: body ? { 'Content-Type': 'application/json' } : {},
            body: body ? JSON.stringify(body) : undefined
        }).then(function (r) {
            if (!r.ok) throw new Error(method + ' ' + path + ' → ' + r.status);
            return r.json();
        });
    }

    function registration() {
        return navigator.serviceWorker.register('/sw.js').then(function () {
            return navigator.serviceWorker.ready;
        });
    }

    function show(state) {
        card.hidden = false;
        btnOn.hidden = state !== 'off';
        btnTest.hidden = btnOff.hidden = state !== 'on';
        if (state === 'ios') sub.textContent = 'באייפון: שתף ← "הוסף למסך הבית", ואז פותחים את האפליקציה משם';
        else if (state === 'denied') sub.textContent = 'ההתראות חסומות בהגדרות הדפדפן';
        else sub.textContent = 'בוקר 08:40 · ערב 21:00, רק אם עוד לא התאמנת';
    }

    function refresh() {
        if (isIos() && !isStandalone()) return Promise.resolve(show('ios'));
        if (Notification.permission === 'denied') return Promise.resolve(show('denied'));
        return registration()
            .then(function (reg) { return reg.pushManager.getSubscription(); })
            .then(function (existing) {
                if (existing) {
                    // Re-send so the server row follows whoever is logged in on this device
                    return api('POST', '/subscribe', existing.toJSON()).then(function () { show('on'); });
                }
                show('off');
            });
    }

    function subscribe() {
        return Notification.requestPermission().then(function (permission) {
            if (permission !== 'granted') {
                if (permission === 'denied') show('denied');
                throw new Error('permission ' + permission);
            }
            return registration();
        }).then(function (reg) {
            return reg.pushManager.getSubscription().then(function (existing) {
                return existing || reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: keyBytes(publicKey)
                });
            });
        }).then(function (subscription) {
            return api('POST', '/subscribe', subscription.toJSON());
        }).then(function () {
            show('on');
        });
    }

    function guard(fn) {
        return function () {
            if (busy) return;
            busy = true;
            Promise.resolve().then(fn).catch(fail).then(function () { busy = false; });
        };
    }

    btnOn.addEventListener('click', guard(function () {
        return subscribe().then(function () { toast('ההתראות פועלות במכשיר הזה'); });
    }));

    btnTest.addEventListener('click', guard(function () {
        return api('POST', '/test').then(function () { toast('נשלחה התראת בדיקה'); });
    }));

    btnOff.addEventListener('click', guard(function () {
        return registration()
            .then(function (reg) { return reg.pushManager.getSubscription(); })
            .then(function (subscription) {
                if (!subscription) return;
                var endpoint = subscription.endpoint;
                return subscription.unsubscribe().then(function () {
                    return api('DELETE', '/subscribe', { endpoint: endpoint });
                });
            })
            .then(function () {
                show('off');
                toast('ההתראות כובו במכשיר הזה', 'בטל', guard(subscribe));
            });
    }));

    api('GET', '/key').then(function (info) {
        if (!info.enabled || !info.public_key) return;
        publicKey = info.public_key;
        return refresh();
    }).catch(function (err) {
        console.error('[arena-push]', err);
    });
})();
