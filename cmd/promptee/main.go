package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/spf13/cobra"
	"github.com/user/promptee/internal/api"
	"github.com/user/promptee/internal/daemon"
	"github.com/user/promptee/internal/tui"
	"golang.org/x/term"
)

const (
	version        = "0.1.0"
	buildDate      = "dev"
	defaultAPIURL  = "http://localhost:8000"
	defaultTopK    = 5
	defaultTradeoff = "balanced"
)

// agentResult is the JSON-serialisable output for headless mode.
type agentResult struct {
	Query   string               `json:"query"`
	Results []api.RecommendResult `json:"results"`
}

var (
	flagAPIURL   string
	flagTopK     int
	flagTradeoff string
	flagAgent    bool
	flagJSON     bool
)

var rootCmd = &cobra.Command{
	Use:     "promptee [query]",
	Short:   "Promptee — Local MLOps & RAG CLI (Codename: Daedalus)",
	Version: version,
	RunE:    run,
}

var buildCmd = &cobra.Command{
	Use:   "build",
	Short: "Zero-day installation: Build and start components",
	RunE: func(cmd *cobra.Command, args []string) error {
		// Default to 'all' if no subcommand provided
		return runBuildAll(cmd, args)
	},
}

var buildCliCmd = &cobra.Command{
	Use:   "cli",
	Short: "Recompile the Go CLI binary",
	RunE:  runBuildCli,
}

var buildBackendCmd = &cobra.Command{
	Use:   "backend",
	Short: "Rebuild and start only the backend Docker container",
	RunE:  runBuildBackend,
}

var buildAllCmd = &cobra.Command{
	Use:   "all",
	Short: "Rebuild backend Docker image and start all services",
	Long: `Rebuilds the backend Docker image and starts all infrastructure services.

The CLI binary is NOT rebuilt here — doing so while Docker is running
can exhaust memory (Go compiler + Docker build + Milvus all compete for RAM).

To rebuild the CLI binary first, use:
  make build            # builds bin/promptee AND copies to ./promptee
  ./promptee build all  # then rebuild Docker + start services
`,
	RunE: func(cmd *cobra.Command, args []string) error {
		return runBuildAll(cmd, args)
	},
}

func init() {
	buildCmd.AddCommand(buildCliCmd, buildBackendCmd, buildAllCmd)
	rootCmd.AddCommand(buildCmd)
	rootCmd.Flags().StringVar(&flagAPIURL, "api-url", defaultAPIURL, "Backend API base URL")
	rootCmd.Flags().IntVar(&flagTopK, "top-k", defaultTopK, "Number of recommendations to return")
	rootCmd.Flags().StringVar(&flagTradeoff, "tradeoff", defaultTradeoff, "Tradeoff preference (balanced|quality|speed)")
	rootCmd.Flags().BoolVar(&flagAgent, "agent", false, "Run in headless agent mode (requires query argument)")
	rootCmd.Flags().BoolVar(&flagJSON, "json", false, "Output results as JSON (headless mode only)")
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	// Resolve script path relative to executable location
	exePath, err := os.Executable()
	if err != nil {
		exePath = "scripts/start_promptee.sh" // fallback to relative path
	} else {
		// bin/promptee -> ../.. -> project root
		projectRoot := filepath.Dir(filepath.Dir(filepath.Dir(exePath)))
		exePath = filepath.Join(projectRoot, "scripts", "start_promptee.sh")
	}

	if err := daemon.EnsureBackendRunning(flagAPIURL, exePath); err != nil {
		fmt.Fprintf(os.Stderr, "warning: backend unavailable: %v\n", err)
	}

	if flagAgent {
		if len(args) == 0 {
			return fmt.Errorf("--agent requires a query argument")
		}
		return runAgentMode(flagAPIURL, args[0], flagTopK, flagTradeoff, flagJSON)
	}

	// Set terminal to raw mode for TUI
	oldState, err := term.MakeRaw(int(os.Stdin.Fd()))
	if err != nil {
		return fmt.Errorf("failed to set raw mode: %w", err)
	}
	defer term.Restore(int(os.Stdin.Fd()), oldState)

	tuiApp := tui.TooeyApp(flagAPIURL, flagTopK, flagTradeoff)
	return tuiApp.Run(context.Background())
}

// runAgentMode performs a single recommendation query and writes results to stdout.
func runAgentMode(apiURL, query string, topK int, tradeoff string, jsonOut bool) error {
	client := api.NewClient(apiURL)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	resp, err := client.Recommend(ctx, api.RecommendRequest{
		Query:              query,
		TopK:               topK,
		TradeoffPreference: tradeoff,
	})
	if err != nil {
		return fmt.Errorf("recommend failed: %w", err)
	}

	// In Agent Mode, we automatically inject the trace token into FullText
	// so the caller/agent always forwards it. Since agent mode doesn't select add-ons yet,
	// we leave addonMode and addonOrder blank or "none".
	for i := range resp.Results {
		traceToken := fmt.Sprintf("\n[PROMPTEE_TRACE:%d:none:]", resp.Results[i].TemplateID)
		resp.Results[i].FullText += traceToken
	}

	if jsonOut {
		return writeJSON(agentResult{Query: query, Results: resp.Results})
	}

	for i, r := range resp.Results {
		fmt.Printf("%d. [%.2f] %s\n", i+1, r.HybridScore, r.Title)
		if r.Objective != "" {
			fmt.Printf("   %s\n", r.Objective)
		}
	}
	return nil
}

// writeJSON encodes v as indented JSON to stdout.
func writeJSON(v any) error {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return fmt.Errorf("json encode: %w", err)
	}
	return nil
}

func getProjectRoot() (string, error) {
	exePath, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("failed to get executable path: %w", err)
	}

	exePath, err = filepath.Abs(exePath)
	if err != nil {
		return "", fmt.Errorf("failed to get absolute path: %w", err)
	}

	// If executable is at project_root/bin/promptee, go up 2 levels
	// If executable is at project_root/promptee, go up 1 level
	candidates := []string{
		filepath.Dir(exePath),           // project_root (if at project_root/promptee)
		filepath.Dir(filepath.Dir(exePath)), // project_root (if at project_root/bin/promptee)
	}

	// Return the first directory that contains go.mod
	for _, candidate := range candidates {
		if _, err := os.Stat(filepath.Join(candidate, "go.mod")); err == nil {
			return candidate, nil
		}
	}

	return "", fmt.Errorf("could not find project root (go.mod not found)")
}

func runBuildCli(cmd *cobra.Command, args []string) error {
	projectRoot, err := getProjectRoot()
	if err != nil {
		return err
	}

	fmt.Println("🔨 Recompiling the Promptee CLI (Go binary)...")
	execCmd := exec.Command("go", "build", "-o", "bin/promptee", "./cmd/promptee")
	execCmd.Stdout = os.Stdout
	execCmd.Stderr = os.Stderr
	execCmd.Dir = projectRoot

	if err := execCmd.Run(); err != nil {
		return fmt.Errorf("go build failed: %w", err)
	}

	fmt.Println("✅ CLI build complete: bin/promptee")

	// Update ./promptee at the project root so the user can run it directly.
	src := filepath.Join(projectRoot, "bin", "promptee")
	dst := filepath.Join(projectRoot, "promptee")
	cpCmd := exec.Command("cp", src, dst)
	cpCmd.Stdout = os.Stdout
	cpCmd.Stderr = os.Stderr
	if err := cpCmd.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "⚠️  Could not copy bin/promptee → ./promptee: %v\n", err)
	} else {
		fmt.Println("✅ Root binary updated: ./promptee")
	}
	return nil
}

func runBuildBackend(cmd *cobra.Command, args []string) error {
	projectRoot, err := getProjectRoot()
	if err != nil {
		return err
	}
	composeFile := filepath.Join(projectRoot, "docker-compose.yml")

	fmt.Println("🐳 Rebuilding Promptee Backend Docker container...")
	execCmd := exec.Command("docker", "compose", "-f", composeFile, "up", "--build", "-d", "backend")
	execCmd.Stdout = os.Stdout
	execCmd.Stderr = os.Stderr
	execCmd.Dir = projectRoot

	if err := execCmd.Run(); err != nil {
		return fmt.Errorf("docker compose failed: %w", err)
	}

	return waitForBackend()
}

func runBuildAll(cmd *cobra.Command, args []string) error {
	projectRoot, err := getProjectRoot()
	if err != nil {
		return err
	}
	composeFile := filepath.Join(projectRoot, "docker-compose.yml")

	if _, err := os.Stat(composeFile); os.IsNotExist(err) {
		return fmt.Errorf("could not find docker-compose.yml at %s", composeFile)
	}

	fmt.Println("🚀 Starting zero-day build and infrastructure deployment...")

	// Step 1: Build only the backend image (the only service with a build: section).
	// Running "up --build -d" for all services simultaneously triggers heavy parallel
	// image pulls (Milvus ~2 GB, MinIO, etcd, postgres) alongside the Docker build,
	// which can exhaust memory and get the process killed by the OS.
	fmt.Println("🐳 Building backend Docker image...")
	buildCmd := exec.Command("docker", "compose", "-f", composeFile, "build", "backend")
	buildCmd.Stdout = os.Stdout
	buildCmd.Stderr = os.Stderr
	buildCmd.Dir = projectRoot
	if err := buildCmd.Run(); err != nil {
		return fmt.Errorf("docker compose build failed: %w", err)
	}

	// Step 2: Start all services (infra images are pulled/cached independently).
	fmt.Println("🐳 Starting all services...")
	upCmd := exec.Command("docker", "compose", "-f", composeFile, "up", "-d")
	upCmd.Stdout = os.Stdout
	upCmd.Stderr = os.Stderr
	upCmd.Dir = projectRoot
	if err := upCmd.Run(); err != nil {
		return fmt.Errorf("docker compose up failed: %w", err)
	}

	return waitForBackend()
}

func waitForBackend() error {
	healthURL := fmt.Sprintf("%s/api/v1/health", flagAPIURL)
	fmt.Printf("⏳ Waiting for backend to become healthy at %s...\n", healthURL)

	timeout := time.After(60 * time.Second)
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-timeout:
			return fmt.Errorf("timeout waiting for backend to become healthy")
		case <-ticker.C:
			resp, err := http.Get(healthURL)
			if err == nil && resp.StatusCode == http.StatusOK {
				resp.Body.Close()
				fmt.Println("✅ Promptee backend is healthy and fully operational!")
				return nil
			}
			if resp != nil {
				resp.Body.Close()
			}
		}
	}
}
