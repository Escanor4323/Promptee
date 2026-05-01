package daemon

import (
	"fmt"
	"net/http"
	"os/exec"
	"time"
)

// CheckDaemonHealth polls the given URL until it returns HTTP 200 or the timeout elapses.
func CheckDaemonHealth(healthURL string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	client := &http.Client{Timeout: 2 * time.Second}
	for time.Now().Before(deadline) {
		resp, err := client.Get(healthURL)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(1 * time.Second)
	}
	return fmt.Errorf("daemon health check failed: %s did not return 200 OK within %s", healthURL, timeout)
}

// EnsureBackendRunning checks the backend heartbeat and launches the daemon if offline.
func EnsureBackendRunning(baseURL string, scriptPath string) error {
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get(baseURL + "/api/v1/health")
	if err == nil && resp.StatusCode == http.StatusOK {
		resp.Body.Close()
		return nil
	}
	cmd := exec.Command("bash", scriptPath)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to launch daemon %s: %w", scriptPath, err)
	}
	return CheckDaemonHealth(baseURL+"/api/v1/health", 30*time.Second)
}
