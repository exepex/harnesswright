package limiter

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestAllowsUpToLimitThenRefuses(t *testing.T) {
	l := New(3, time.Minute)
	for i := 0; i < 3; i++ {
		if !l.Allow("a") {
			t.Fatalf("request %d refused, want allowed", i+1)
		}
	}
	if l.Allow("a") {
		t.Fatal("fourth request allowed, want refused")
	}
}

func TestNewWindowResetsCount(t *testing.T) {
	now := time.Unix(0, 0)
	l := New(1, time.Minute)
	l.now = func() time.Time { return now }
	l.Allow("a")
	now = now.Add(time.Minute)
	if !l.Allow("a") {
		t.Fatal("request in new window refused, want allowed")
	}
}

func TestRefusedRequestGets429(t *testing.T) {
	l := New(0, time.Minute)
	handler := l.Middleware(func(*http.Request) string { return "a" },
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("status %d, want 429", rec.Code)
	}
}
