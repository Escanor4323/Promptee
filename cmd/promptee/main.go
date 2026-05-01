package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
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

func init() {
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
