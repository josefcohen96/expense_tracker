// Service Worker for Performance Optimization and Caching

// Bump versions to force update on clients
const CACHE_NAME = 'expense-tracker-v1.0.4';
const STATIC_CACHE = 'static-v1.0.4';
const DYNAMIC_CACHE = 'dynamic-v1.0.4';

// Files to cache immediately
const STATIC_FILES = [
    '/static/css/main.css',
    '/static/js/core/animations.js',
    '/static/js/vendor/htmx.min.js',
    '/static/js/vendor/chart.umd.min.js'
    // External CDNs are not pre-cached to avoid CORS issues; they load via browser cache
];

// Install event - cache static files
self.addEventListener('install', event => {
    console.log('Service Worker installing...');
    
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => {
                console.log('Caching static files');
                return cache.addAll(STATIC_FILES);
            })
            .then(() => {
                console.log('Static files cached successfully');
                return self.skipWaiting();
            })
            .catch(error => {
                console.error('Error caching static files:', error);
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    console.log('Service Worker activating...');
    
    event.waitUntil(
        caches.keys()
            .then(cacheNames => {
                return Promise.all(
                    cacheNames.map(cacheName => {
                        if (cacheName !== STATIC_CACHE && cacheName !== DYNAMIC_CACHE) {
                            console.log('Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            })
            .then(() => {
                console.log('Service Worker activated');
                return self.clients.claim();
            })
    );
});

// Fetch event - serve from cache when possible
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);
    // Trace key navigations (avoid noise for static)
    if (request.headers.get('accept')?.includes('text/html') || url.pathname === '/login') {
        console.log('[SW] fetch', request.method, url.pathname, { mode: request.mode, redirect: request.redirect });
    }
    
    // If user logs out, proactively clear all dynamic caches to avoid stale UI
    if (url.pathname === '/logout') {
        event.respondWith((async () => {
            try {
                const cacheNames = await caches.keys();
                await Promise.all(
                    cacheNames.map(name => {
                        if (name !== STATIC_CACHE && name !== DYNAMIC_CACHE) {
                            return caches.delete(name);
                        }
                        return Promise.resolve();
                    })
                );
                // Also clear dynamic cache explicitly
                await caches.delete(DYNAMIC_CACHE);
            } catch (e) {
                // no-op
            }
            // Let the network handle the redirect to /login
            return fetch(request);
        })());
        return;
    }

    // Skip non-GET requests, but log login POSTs for debugging
    if (request.method !== 'GET') {
        if (url.pathname === '/login') {
            console.log('[SW] bypassing non-GET for /login');
        }
        return;
    }
    
    // Skip external requests (except CDN resources)
    if (!url.origin.includes(location.origin) && 
        !url.href.includes('cdn.tailwindcss.com') && 
        !url.href.includes('cdnjs.cloudflare.com')) {
        return;
    }
    
    // Handle API requests
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(handleApiRequest(request));
        return;
    }
    
    // Handle static files
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(handleStaticRequest(request));
        return;
    }
    
    // Handle HTML pages: network-only (do not cache navigations)
    if (request.headers.get('accept')?.includes('text/html')) {
        event.respondWith((async () => {
            try {
                const response = await fetch(request);
                const finalUrl = new URL(response.url);
                if (finalUrl.pathname !== url.pathname) {
                    console.log('[SW] navigation redirected', { from: url.pathname, to: finalUrl.pathname });
                }
                // If we were redirected to /login, try to purge any stale cached entry for the requested page
                if (response.redirected || finalUrl.pathname === '/login') {
                    try {
                        const cache = await caches.open(DYNAMIC_CACHE);
                        await cache.delete(request, { ignoreSearch: true });
                    } catch (e) { /* no-op */ }
                }
                return response;
            } catch (error) {
                console.log('HTML request failed, trying cache as last resort:', error);
                // Fallback to offline page if available
                const offline = await caches.match('/offline.html');
                if (offline) return offline;
                return new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
            }
        })());
        return;
    }
    
    // Default: try cache first, then network
    event.respondWith(handleDefaultRequest(request));
});

// Handle API requests - network first, cache fallback
async function handleApiRequest(request) {
    try {
        const response = await fetch(request);
        
        // Cache successful API responses
        if (response.ok) {
            const cache = await caches.open(DYNAMIC_CACHE);
            cache.put(request, response.clone());
        }
        
        return response;
    } catch (error) {
        console.log('API request failed, trying cache:', error);
        
        // Try to serve from cache
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return offline response
        return new Response(JSON.stringify({ error: 'Offline' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Handle static files - cache first, network fallback
async function handleStaticRequest(request) {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
        return cachedResponse;
    }
    
    try {
        const response = await fetch(request);
        
        if (response.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, response.clone());
        }
        
        return response;
    } catch (error) {
        console.log('Static file request failed:', error);
        return new Response('Not found', { status: 404 });
    }
}

// (Removed) HTML caching logic — navigations are now network-only to prevent stale auth state

// Handle default requests - cache first, network fallback
async function handleDefaultRequest(request) {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
        return cachedResponse;
    }
    
    try {
        const response = await fetch(request);
        
        if (response.ok) {
            const cache = await caches.open(DYNAMIC_CACHE);
            cache.put(request, response.clone());
        }
        
        return response;
    } catch (error) {
        console.log('Request failed:', error);
        return new Response('Not found', { status: 404 });
    }
}

// Background sync for offline actions
self.addEventListener('sync', event => {
    if (event.tag === 'background-sync') {
        event.waitUntil(doBackgroundSync());
    }
});

async function doBackgroundSync() {
    try {
        // Sync any pending data when connection is restored
        console.log('Performing background sync...');
        
        // You can add specific sync logic here
        // For example, sync offline transactions
        
    } catch (error) {
        console.error('Background sync failed:', error);
    }
}

// Push notifications (if needed)
self.addEventListener('push', event => {
    if (event.data) {
        const data = event.data.json();
        
        const options = {
            body: data.body,
            icon: '/static/images/icon-192x192.png',
            badge: '/static/images/badge-72x72.png',
            vibrate: [100, 50, 100],
            data: {
                dateOfArrival: Date.now(),
                primaryKey: 1
            },
            actions: [
                {
                    action: 'explore',
                    title: 'View',
                    icon: '/static/images/checkmark.png'
                },
                {
                    action: 'close',
                    title: 'Close',
                    icon: '/static/images/xmark.png'
                }
            ]
        };
        
        event.waitUntil(
            self.registration.showNotification(data.title, options)
        );
    }
});

// Handle notification clicks
self.addEventListener('notificationclick', event => {
    event.notification.close();
    
    if (event.action === 'explore') {
        event.waitUntil(
            clients.openWindow('/')
        );
    }
});

// Performance monitoring
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'GET_VERSION') {
        event.ports[0].postMessage({ version: CACHE_NAME });
    }
});
