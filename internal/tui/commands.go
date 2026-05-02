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
	err error
}

type simulateResponseMsg struct {
	query string
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
	return feedbackResultMsg{err: err}
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
	case "/ingest":
		if arg == "" {
			return dispatchResult{msg: "Usage: /ingest <path>"}
		}
		return dispatchResult{
			cmd: func() app.Msg { return doIngest(client, arg) },
			msg: "Ingesting: " + arg,
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

func formatFinalPrompt(item RecommendItem, values map[string]string) string {
	filled := item.FullText
	for v, val := range values {
		filled = fillVariable(filled, v, val)
	}
	remaining := prompt.ParseVariables(filled)
	if len(remaining) > 0 {
		filled += "\n\nUnfilled variables: " + strings.Join(remaining, ", ")
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
	return `Available commands:
 /ingest <path>     — Ingest file/directory into vector store
 /copy              — Copy filled prompt to clipboard
 /telemetry         — Show telemetry info
 /feedback <1-5>    — Rate last execution (1-5 stars)
 /daemon start|stop|status — Manage backend daemon
 /health            — Check backend health
 /clear             — Clear transcript
 /help              — Show this help
 /quit              — Exit Promptee

 Type anything else to search for prompt recommendations.
 After results appear, press 1-9 to select one.`
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

var _ = fmt.Sprintf
