package daemon

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestCheckDaemonHealth_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	err := CheckDaemonHealth(srv.URL, 2*time.Second)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestCheckDaemonHealth_Timeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	err := CheckDaemonHealth(srv.URL, 1*time.Second)
	if err == nil {
		t.Fatal("expected timeout error")
	}
}

func TestEnsureBackendRunning_AlreadyRunning(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	err := EnsureBackendRunning(srv.URL, "/nonexistent/script.sh")
	if err != nil {
		t.Fatalf("expected no error when backend is running, got %v", err)
	}
}
