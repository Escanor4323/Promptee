package tui

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/stukennedy/tooey/app"
	"github.com/user/promptee/internal/api"
	"github.com/user/promptee/internal/prompt"
)

// getClipboardKeybindings returns platform-specific clipboard shortcuts
func getClipboardKeybindings() (copy, paste string) {
	if runtime.GOOS == "darwin" {
		return "Cmd+C", "Cmd+V"
	}
	return "Ctrl+Shift+C", "Ctrl+Shift+V"
}

type recommendResultMsg struct {
	resp *api.RecommendResponse
	err  error
}

type ingestResultMsg struct {
	resp *api.IngestResponse
	err  error
}

type healthResultMsg struct {
	err      error
	explicit bool
}

type telemetryResultMsg struct {
	resp *api.TelemetryResponse
	err  error
}

type feedbackResultMsg struct {
	err   error
	score int
}

type simulateResponseMsg struct {
	query string
}

type addonRegisterResultMsg struct {
	addon *api.RegisterAddonResponse
	err   error
}

type addonRecommendResultMsg struct {
	results []api.AddonRecommendResult
	err     error
}

type telemetrySummaryResultMsg struct {
	resp *api.TelemetrySummaryResponse
	err  error
}

type modelsListResultMsg struct {
	models []string
	err    error
}

type modelRegisterResultMsg struct {
	model *api.ModelResponse
	err   error
}

type tickMsg time.Time

// newTickCmd returns a Cmd that sends tickMsg after one second.
func newTickCmd() app.Msg {
	time.Sleep(time.Second)
	return tickMsg(time.Now())
}

type animTickMsg struct{}

func newAnimTickCmd() app.Msg {
	time.Sleep(80 * time.Millisecond)
	return animTickMsg{}
}

func doRecommend(client *api.Client, query string, topK int, tradeoffPreference string) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	resp, err := client.Recommend(ctx, api.RecommendRequest{
		Query:              query,
		TopK:               topK,
		TradeoffPreference: tradeoffPreference,
	})
	return recommendResultMsg{resp: resp, err: err}
}

func doIngest(client *api.Client, path string) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	req := api.IngestRequest{}
	if strings.HasSuffix(path, "/") || strings.HasSuffix(path, "\\") {
		req.Directory = strings.TrimRight(path, "/\\")
	} else {
		req.Paths = []string{path}
	}
	resp, err := client.Ingest(ctx, req)
	return ingestResultMsg{resp: resp, err: err}
}

func doBatchIngest(client *api.Client, paths []string) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	req := api.IngestRequest{Paths: paths}
	resp, err := client.Ingest(ctx, req)
	return ingestResultMsg{resp: resp, err: err}
}

func doHealthCheck(client *api.Client) app.Msg {
	return healthResultMsg{err: client.CheckHealth(), explicit: true}
}

func doHealthCheckBg(client *api.Client) app.Msg {
	return healthResultMsg{err: client.CheckHealth(), explicit: false}
}

func doSubmitTelemetry(client *api.Client, templateID int, latencyMs float64, addonMode, modelID string) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	resp, err := client.SubmitTelemetry(ctx, api.TelemetryRequest{
		TemplateID: templateID,
		LatencyMs:  latencyMs,
		Verbosity:  "moderate",
		AddonMode:  addonMode,
		ModelID:    modelID,
	})
	return telemetryResultMsg{resp: resp, err: err}
}

func doSubmitFeedback(client *api.Client, executionID int, qualityScore int, notes string) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	err := client.SubmitFeedback(ctx, api.FeedbackRequest{
		ExecutionID:  executionID,
		QualityScore: qualityScore,
		Notes:        notes,
	})
	return feedbackResultMsg{err: err, score: qualityScore}
}

func doRegisterAddon(client *api.Client, mode, name, filePath string) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	content, err := os.ReadFile(filePath)
	if err != nil {
		return addonRegisterResultMsg{err: fmt.Errorf("read file %s: %w", filePath, err)}
	}
	resp, err := client.RegisterAddon(ctx, api.RegisterAddonRequest{
		Name:        name,
		Mode:        mode,
		Suffix:      string(content),
		Description: fmt.Sprintf("Custom add-on: %s", name),
	})
	return addonRegisterResultMsg{addon: resp, err: err}
}

func doRecommendAddons(client *api.Client, query string) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	resp, err := client.RecommendAddons(ctx, api.AddonRecommendRequest{Query: query, TopK: 5})
	if err != nil {
		return addonRecommendResultMsg{err: err}
	}
	return addonRecommendResultMsg{results: resp.Results}
}

func doSimulateResponse(query string) app.Msg {
	time.Sleep(600 * time.Millisecond)
	return simulateResponseMsg{query: query}
}

func doGetTelemetrySummary(client *api.Client) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	resp, err := client.GetTelemetrySummary(ctx)
	return telemetrySummaryResultMsg{resp: resp, err: err}
}

func doFetchModels(client *api.Client) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	models, err := client.ListModels(ctx)
	return modelsListResultMsg{models: models, err: err}
}

func doRegisterModel(client *api.Client, name, modelType string) app.Msg {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	model, err := client.RegisterModel(ctx, api.RegisterModelRequest{Name: name, Type: modelType})
	return modelRegisterResultMsg{model: model, err: err}
}

type dispatchResult struct {
	cmd func() app.Msg
	msg string
}

func dispatchCommand(input string, client *api.Client, topK int, tradeoffPreference string) dispatchResult {
	input = strings.TrimSpace(input)
	if input == "" {
		return dispatchResult{}
	}

	if !strings.HasPrefix(input, "/") {
		return dispatchResult{
			cmd: func() app.Msg { return doRecommend(client, input, topK, tradeoffPreference) },
			msg: "Querying: " + input,
		}
	}

	parts := strings.Fields(input)
	cmd := strings.ToLower(parts[0])
	arg := ""
	if len(parts) > 1 {
		arg = strings.Join(parts[1:], " ")
	}

	switch cmd {
	case "/add":
		if arg == "" {
			return dispatchResult{msg: "Usage: /add <path> [path2 ...]"}
		}
		paths := strings.Fields(arg)
		if len(paths) == 1 {
			return dispatchResult{
				cmd: func() app.Msg { return doIngest(client, paths[0]) },
				msg: "Adding: " + paths[0],
			}
		}
		return dispatchResult{
			cmd: func() app.Msg { return doBatchIngest(client, paths) },
			msg: fmt.Sprintf("Adding batch: %d paths", len(paths)),
		}
	case "/add-addon":
		if arg == "" {
			return dispatchResult{msg: "Usage: /add-addon <mode> <name> <file-path>\n  mode: speed|quality|cost"}
		}
		parts := strings.SplitN(arg, " ", 3)
		if len(parts) < 3 {
			return dispatchResult{msg: "Usage: /add-addon <mode> <name> <file-path>"}
		}
		addonMode, addonName, filePath := parts[0], parts[1], parts[2]
		return dispatchResult{
			cmd: func() app.Msg { return doRegisterAddon(client, addonMode, addonName, filePath) },
			msg: fmt.Sprintf("Registering add-on [%s] %s...", addonMode, addonName),
		}
	case "/health":
		return dispatchResult{
			cmd: func() app.Msg { return doHealthCheck(client) },
			msg: "Checking health...",
		}
	case "/feedback":
		if arg == "" {
			return dispatchResult{msg: "Usage: /feedback <1-5> [notes]"}
		}
		return dispatchResult{msg: "Use number keys 1-5 after a recommendation to rate it"}
	case "/telemetry":
		return dispatchResult{msg: formatTelemetryHelp()}
	case "/daemon":
		return dispatchResult{msg: formatDaemonHelp(arg)}
	case "/model":
		if arg == "" {
			return dispatchResult{msg: "Usage: /model <model-name> or /model to display current"}
		}
		return dispatchResult{
			cmd: func() app.Msg { return doRegisterModel(client, arg, "claude") },
			msg: "Registering model: " + arg,
		}
	case "/add-model":
		if arg == "" {
			return dispatchResult{msg: "Usage: /add-model <model-name>"}
		}
		return dispatchResult{
			cmd: func() app.Msg { return doRegisterModel(client, arg, "claude") },
			msg: "Adding model: " + arg,
		}
	case "/clear":
		return dispatchResult{msg: "__clear__"}
	case "/test-clipboard":
		return dispatchResult{msg: formatClipboardDiagnostics()}
	case "/help":
		return dispatchResult{msg: formatHelpText()}
	case "/quit":
		return dispatchResult{msg: "__quit__"}
	default:
		return dispatchResult{msg: "Unknown command: " + cmd + ". Type /help for available commands."}
	}
}

func selectRecommendation(seg RecommendSegment, num int) (RecommendItem, bool) {
	for _, item := range seg.Items {
		if item.Index == num {
			return item, true
		}
	}
	return RecommendItem{}, false
}

func fillVariable(templateText, varName, value string) string {
	return strings.ReplaceAll(templateText, "["+varName+"]", value)
}

func formatFinalPrompt(item RecommendItem, values map[string]string, injectTrace bool, addonMode, addonOrder string) string {
	filled := item.FullText
	for v, val := range values {
		filled = fillVariable(filled, v, val)
	}
	remaining := prompt.ParseVariables(filled)
	if len(remaining) > 0 {
		filled += "\n\nUnfilled variables: " + strings.Join(remaining, ", ")
	}
	if injectTrace {
		filled += fmt.Sprintf("\n[PROMPTEE_TRACE:%d:%s:%s]", item.TemplateID, addonMode, addonOrder)
	}
	return filled
}

func parseNumSelection(input string) (int, bool) {
	n, err := strconv.Atoi(strings.TrimSpace(input))
	if err != nil || n < 1 || n > 9 {
		return 0, false
	}
	return n, true
}

func formatHelpText() string {
	copyKey, pasteKey := getClipboardKeybindings()
	return fmt.Sprintf(`Available commands:
 /add <path> [path2 ...]  — Add prompt file(s) to vector store
 /add-addon <mode> <name> <file>  — Register a custom add-on (mode: speed|quality|cost)
 /model <name>            — Switch active model for telemetry tracking
 /add-model <name>        — Register new model in backend
 /copy                    — Copy filled prompt to clipboard
 /telemetry               — Show telemetry info
 /feedback <1-5>          — Rate last execution (1-5 stars)
 /daemon start|stop|status — Manage backend daemon
 /health                  — Check backend health
 /clear                   — Clear transcript
 /help                    — Show this help
 /quit                    — Exit Promptee

 Clipboard:
   %s  — Copy selected prompt to system clipboard
   %s  — Paste from clipboard into input (bracketed paste mode)

 Type anything else to search for prompt recommendations.
 After results appear, press 1-9 to select one.`, copyKey, pasteKey)
}

func formatTelemetryHelp() string {
	return `**Telemetry & Feedback System**

Promptee automatically tracks execution metrics to optimize future recommendations:

  **Captured Metrics:**
    • Latency — How fast the prompt executed
    • Token Usage — Input/output token counts (COST optimization)
    • Context Window % — Memory efficiency
    • Quality Score — Your 1-5 star feedback

  **Optimization Strategy:**
    The system maps these metrics to developer tradeoffs:
      SPEED  — Low latency + token usage
      COST   — Minimal input/output tokens
      QUALITY — High quality scores from feedback

  **How It Works:**
    1. You select a prompt + optional add-on
    2. Promptee records execution metrics
    3. You rate it (1-5 stars) after execution
    4. The rating boosts similar prompts in future searches
    5. Recommendations get smarter over time

  **Your Action:**
    After executing a prompt, press 1-5 to rate it. This helps Promptee
    learn what works best for your workflow. No rating needed if you skip.`
}

func formatDaemonHelp(arg string) string {
	switch strings.ToLower(arg) {
	case "start":
		return "Starting daemon... (run `./promptee daemon start` in another terminal)"
	case "stop":
		return "Stopping daemon... (run `make stop` in another terminal)"
	case "status":
		return "Checking daemon status... (use /health)"
	default:
		return "Usage: /daemon start|stop|status"
	}
}

func formatClipboardDiagnostics() string {
	// Test paste function
	text, err := pasteFromClipboard()
	var pasteStatus string
	if err != nil {
		pasteStatus = fmt.Sprintf("❌ Paste failed: %v", err)
	} else if text == "" {
		pasteStatus = "⚠ Clipboard is empty"
	} else {
		pasteStatus = fmt.Sprintf("✓ Clipboard has %d bytes: %q", len(text), text[:min(len(text), 50)])
	}

	copyKey, pasteKey := getClipboardKeybindings()
	return fmt.Sprintf(`**Clipboard Diagnostics**

Platform: %s (uses %s for paste, %s for copy)

Paste Status: %s

**How to test:**
1. Copy something to clipboard: %s+C (or use your OS copy)
2. In Promptee, press: %s
3. Check if text appears in the input field

If nothing appears, the issue is likely:
- Keyboard shortcut not being detected by terminal
- Terminal not forwarding the key event to the app
- Try using /paste command instead (manual paste via bracketed paste)`, runtime.GOOS, pasteKey, copyKey, pasteStatus, copyKey, pasteKey)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func copyToClipboard(text string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("pbcopy")
	case "linux":
		cmd = exec.Command("xclip", "-selection", "clipboard")
	case "windows":
		cmd = exec.Command("powershell", "-Command", fmt.Sprintf("Set-Clipboard -Value $input"))
	default:
		return fmt.Errorf("clipboard not supported on %s", runtime.GOOS)
	}
	cmd.Stdin = strings.NewReader(text)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func pasteFromClipboard() (string, error) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("pbpaste")
	case "linux":
		cmd = exec.Command("xclip", "-selection", "clipboard", "-o")
	case "windows":
		cmd = exec.Command("powershell", "-Command", "Get-Clipboard")
	default:
		return "", fmt.Errorf("clipboard not supported on %s", runtime.GOOS)
	}
	output, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("paste failed: %w", err)
	}
	return string(output), nil
}

var _ = fmt.Sprintf
