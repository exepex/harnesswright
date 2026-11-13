// Package limiter caps each client at a fixed number of requests per window.
package limiter

import (
	"net/http"
	"sync"
	"time"
)

// Limiter counts requests per client in fixed windows.
type Limiter struct {
	mu     sync.Mutex
	limit  int
	window time.Duration
	now    func() time.Time
	counts map[string]int
	start  map[string]time.Time
}

// New returns a limiter allowing limit requests per window for each client.
func New(limit int, window time.Duration) *Limiter {
	return &Limiter{limit: limit, window: window, now: time.Now,
		counts: map[string]int{}, start: map[string]time.Time{}}
}

// Allow reports whether the client may make one more request now.
func (l *Limiter) Allow(client string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := l.now()
	if now.Sub(l.start[client]) >= l.window {
		l.start[client], l.counts[client] = now, 0
	}
	if l.counts[client] >= l.limit {
		return false
	}
	l.counts[client]++
	return true
}

// Middleware answers 429 Too Many Requests once a client is over its limit.
func (l *Limiter) Middleware(client func(*http.Request) string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !l.Allow(client(r)) {
			http.Error(w, "too many requests", http.StatusTooManyRequests)
			return
		}
		next.ServeHTTP(w, r)
	})
}
