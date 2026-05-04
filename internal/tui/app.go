package tui

import (
	"fmt"
	"strconv"
	"strings"

	"github.com/stukennedy/tooey/app"
	"github.com/stukennedy/tooey/component"
	"github.com/stukennedy/tooey/input"
	"github.com/stukennedy/tooey/node"
	"github.com/user/promptee/internal/api"
	"github.com/user/promptee/internal/prompt"
	"github.com/user/promptee/internal/telemetry"
)

const splashArt = ` /$$$$$$$                                               /$$
| $$__  $$                                             | $$
| $$  \ $$ /$$$$$$   /$$$$$$  /$$$$$$/$$$$   /$$$$$$  /$$$$$$    /$$$$$$   /$$$$$$
| $$$$$$$//$$__  $$ /$$__  $$| $$_  $$_  $$ /$$__  $$|_  $$_/   /$$__  $$ /$$__  $$
| $$____/| $$  \__/| $$  \ $$| $$ \ $$ \ $$| $$  \ $$  | $$    | $$$$$$$$| $$$$$$$$
| $$     | $$      | $$  | $$| $$ | $$ | $$| $$  | $$  | $$ /$$| $$_____/| $$_____/
| $$     | $$      |  $$$$$$/| $$ | $$ | $$| $$$$$$$/  |  $$$$/|  $$$$$$$|  $$$$$$$
|__/     |__/       \______/ |__/ |__/ |__/| $$____/    \___/   \_______/ \_______/
                                           | $$
                                           | $$
                                           |__/`

type inputMode int

const (
	modeQuery inputMode = iota
	modeSelectConfirm
	modeAddonSelect
	modeAddonDescribe
	modeVarFill
)

// Model holds all application state for the tooey-based TUI.
type Model struct {
	client                   *api.Client
	chatInput                component.TextInput
	convo                    *Transcript
	spinner                  SpinnerState
	timer                    *telemetry.Timer
	scrollOff                int
	mode                     inputMode
	width                    int
	height                   int
	backendOnline            bool
	lastQuery                string
	topK                     int
	tradeoffPreference       string
	lastSeg                  *RecommendSegment
	healthCheckCounter       int
	needsInitialHealthCheck  bool
	needsDashboardLoad       bool
	dashboardDisplayed       bool
	selectedItem             RecommendItem
	varsToFill               []string
	varFillIdx               int
	varValues                map[string]string
	availableAddons          []api.AddOn
	lastLatencyMs            float64
	lastTemplateID           int
	lastExecutionID          int
	lastAddonMode            string
	lastAddonName            string
	currentModel             string
	availableModels          []string
	thinking                 bool
	lastSummary              *api.TelemetrySummaryResponse
	selectAnimFrame          int
	queryAnimFrame           int
	addonSelectAnimFrame     int
	addonDescribeAnimFrame   int
	varFillAnimFrame         int
	animRunning              bool
	justFoundResults         bool
	lastFeedbackScore        int
	awaitingFeedback         bool
	activeJobID              string
	polling                  bool
	pollAttempts             int
}

// NewModel creates the initial application model.
func NewModel(apiURL string, topK int, tradeoffPreference string) *Model {
	return &Model{
		client:            api.NewClient(apiURL),
		chatInput:         component.NewTextInput("Type a query or /help for commands..."),
		convo:             NewTranscript(),
		spinner:           NewSpinnerState(),
		topK:              topK,
		tradeoffPreference: tradeoffPreference,
		mode:              modeQuery,
		varValues:         make(map[string]string),
		currentModel:      "claude-opus-4-7",
		availableModels:   []string{"claude-opus-4-7", "claude-sonnet-4-6"},
	}
}

// TooeyApp returns an app.App wired to this model's Init/Update/View.
// Clipboard: Use Ctrl+Shift+C to copy, Ctrl+Shift+V to paste (avoids SIGINT collision with Ctrl+C).
// Bracketed paste mode is enabled to safely handle multi-line clipboard content.
func TooeyApp(apiURL string, topK int, tradeoffPreference string) *app.App {
	mdl := NewModel(apiURL, topK, tradeoffPreference)
	mdl.needsInitialHealthCheck = true
	mdl.needsDashboardLoad = true
	return &app.App{
		Init: func() interface{} {
			mdl.width, mdl.height = input.TermSize()
			// Enable bracketed paste mode (\x1b[?2004h): terminal wraps pastes with \x1b[200~ ... \x1b[201~
			// This signals the app to treat pasted text as a single block, preventing format breaks
			fmt.Print("\x1b[?2004h")
			return mdl
		},
		Update: func(m interface{}, msg app.Msg) app.UpdateResult {
			return m.(*Model).update(msg)
		},
		View: func(m interface{}, focused string) node.Node {
			return m.(*Model).view(focused)
		},
	}
}

// needsAnimation returns true if the current mode and state require animation
// and animation is not already running.
func (m *Model) needsAnimation() bool {
	if m.animRunning {
		return false
	}
	if m.chatInput.Value != "" {
		return false
	}
	switch m.mode {
	case modeQuery, modeSelectConfirm, modeAddonSelect, modeAddonDescribe, modeVarFill:
		return true
	}
	return false
}

// update is the central message dispatcher for the tooey App.
func (m *Model) update(msg app.Msg) app.UpdateResult {
	if m.needsInitialHealthCheck {
		m.needsInitialHealthCheck = false
		return app.UpdateResult{
			Model: m,
			Cmds: []app.Cmd{
				func() app.Msg {
					return doHealthCheckBg(m.client)
				},
				newTickCmd,
				func() app.Msg { return newAnimTickCmd() },
			},
		}
	}

	switch msg := msg.(type) {
	case app.ResizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case app.KeyMsg:
		return m.handleKey(msg)

	case app.ScrollMsg:
		m.scrollOff += msg.Delta
		if m.scrollOff < 0 {
			m.scrollOff = 0
		}
		return app.NoCmd(m)

	case app.FocusMsg:
		m.chatInput.Focused = msg.Focused
		return app.NoCmd(m)

	case app.PasteMsg:
		if !m.thinking {
			m.chatInput = m.chatInput.Paste(msg.Text)
		}
		return app.NoCmd(m)

	case recommendResultMsg:
		return m.handleRecommendResult(msg)

	case ingestResultMsg:
		return m.handleIngestResult(msg)

	case ingestEnqueueResultMsg:
		return m.handleIngestEnqueueResult(msg)

	case jobProgressMsg:
		return m.handleJobProgress(msg)

	case addonRegisterResultMsg:
		return m.handleAddonRegisterResult(msg)

	case addonRecommendResultMsg:
		return m.handleAddonRecommendResult(msg)

	case healthResultMsg:
		m.backendOnline = msg.err == nil
		if m.needsDashboardLoad {
			m.needsDashboardLoad = false
			if m.backendOnline {
				if msg.explicit {
					m.convo.Add(TextSegment{Text: "[ok] Backend online"})
				}
				return app.UpdateResult{
					Model: m,
					Cmds: []app.Cmd{
						func() app.Msg { return doGetTelemetrySummary(m.client) },
						func() app.Msg { return doFetchModels(m.client) },
					},
				}
			} else {
				m.convo.Add(ErrorSegment{Message: "Backend offline -- run /daemon start or ./promptee daemon start"})
				m.convo.Add(TextSegment{Text: ""})
				m.convo.Add(SplashArtSegment{Text: splashArt})
				m.convo.Add(TextSegment{Text: " Promptee — Local MLOps & RAG CLI (Codename: Daedalus)"})
				m.convo.Add(TextSegment{Text: ""})
			}
		} else if msg.explicit {
			if m.backendOnline {
				m.convo.Add(TextSegment{Text: "[ok] Backend online"})
			} else {
				m.convo.Add(ErrorSegment{Message: "Backend offline"})
			}
		}
		return app.NoCmd(m)

	case simulateResponseMsg:
		m.convo.Add(AssistantMsgSegment{Text: "Backend offline. Simulated response for: " + msg.query})
		m.spinner.SetStatus(StatusComplete, "Simulated")
		m.thinking = false
		return app.NoCmd(m)

	case telemetryResultMsg:
		if msg.err != nil {
			m.convo.Add(ErrorSegment{Message: fmt.Sprintf("telemetry error: %s", msg.err.Error())})
		} else if msg.resp != nil {
			m.lastExecutionID = msg.resp.ID
			m.convo.Add(TextSegment{Text: fmt.Sprintf(
				"[ok] Telemetry recorded (execution #%d)  speed=%.2f cost=%.2f quality=%.2f",
				msg.resp.ID,
				msg.resp.TradeoffSpeed,
				msg.resp.TradeoffCost,
				msg.resp.TradeoffQuality,
			)})
		}
		return app.NoCmd(m)

	case feedbackResultMsg:
		if msg.err != nil {
			m.convo.Add(ErrorSegment{Message: msg.err.Error()})
		} else {
			m.lastFeedbackScore = msg.score
			m.awaitingFeedback = false
			m.convo.Add(TextSegment{Text: "[ok] Feedback recorded"})
		}
		return app.NoCmd(m)

	case telemetrySummaryResultMsg:
		m.lastSummary = msg.resp
		m.convo.RemoveFirst()
		if msg.resp != nil {
			m.convo.Add(DashboardSegment{
				TotalExecutions: msg.resp.TotalExecutions,
				AvgQualityScore: msg.resp.AvgQualityScore,
				ByCategory:      msg.resp.ByCategory,
				Percentages:     msg.resp.Percentages,
			})
		}
		m.convo.Add(TextSegment{Text: ""})
		m.convo.Add(SplashArtSegment{Text: splashArt})
		m.convo.Add(TextSegment{Text: " Promptee — Local MLOps & RAG CLI (Codename: Daedalus)"})
		m.convo.Add(TextSegment{Text: ""})
		m.dashboardDisplayed = true
		return app.NoCmd(m)

	case modelsListResultMsg:
		if msg.err != nil {
			m.convo.Add(ErrorSegment{Message: fmt.Sprintf("failed to fetch models: %s", msg.err.Error())})
		} else if msg.models != nil && len(msg.models) > 0 {
			m.availableModels = msg.models
			m.convo.Add(TextSegment{Text: fmt.Sprintf("[ok] Loaded %d models", len(msg.models))})
		}
		return app.NoCmd(m)

	case modelRegisterResultMsg:
		if msg.err != nil {
			m.convo.Add(ErrorSegment{Message: fmt.Sprintf("failed to register model: %s", msg.err.Error())})
		} else if msg.model != nil {
			m.currentModel = msg.model.Name
			m.convo.Add(TextSegment{Text: fmt.Sprintf("[ok] Model registered: %s", msg.model.Name)})
		}
		return app.NoCmd(m)

	case templatesListResultMsg:
		m.thinking = false
		m.spinner.SetStatus(StatusComplete, "Listed")
		if msg.err != nil {
			m.convo.Add(ErrorSegment{Message: fmt.Sprintf("list failed: %s", msg.err.Error())})
		} else {
			m.convo.Add(TextSegment{Text: formatTemplateList(msg.items, msg.sortBy)})
		}
		return app.NoCmd(m)

	case tickMsg:
		if m.spinner.Kind != StatusIdle && m.spinner.Kind != StatusComplete {
			m.spinner.Tick()
		}
		m.healthCheckCounter++

		var cmds []app.Cmd
		cmds = append(cmds, newTickCmd)

		// Restart animation if we're in a mode that needs it but animation isn't running
		if m.needsAnimation() {
			cmds = append(cmds, func() app.Msg { return newAnimTickCmd() })
		}

		if m.healthCheckCounter >= 5 {
			m.healthCheckCounter = 0
			cmds = append(cmds, func() app.Msg { return doHealthCheckBg(m.client) })
		}

		if m.polling && m.activeJobID != "" {
			jobID := m.activeJobID
			cmds = append(cmds, doPollJob(m.client, jobID))
		}

		return app.UpdateResult{Model: m, Cmds: cmds}

	case animTickMsg:
		shouldContinue := false
		m.animRunning = true

		switch m.mode {
		case modeSelectConfirm:
			// Continuous animation - frame counter increments indefinitely
			// renderAnimatedInput calculates the oscillating position
			m.selectAnimFrame++
			shouldContinue = true
		case modeQuery:
			// Continuous animation while input is empty
			if m.chatInput.Value == "" {
				m.queryAnimFrame++
				shouldContinue = true
			}
		case modeAddonSelect:
			// Continuous animation while input is empty
			if m.chatInput.Value == "" {
				m.addonSelectAnimFrame++
				shouldContinue = true
			}
		case modeAddonDescribe:
			// Continuous animation while input is empty
			if m.chatInput.Value == "" {
				m.addonDescribeAnimFrame++
				shouldContinue = true
			}
		case modeVarFill:
			// Continuous animation while input is empty
			if m.chatInput.Value == "" {
				m.varFillAnimFrame++
				shouldContinue = true
			}
		}

		if shouldContinue {
			return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
		}
		m.animRunning = false
		return app.NoCmd(m)
	}

	return app.NoCmd(m)
}

// handleKey processes all keyboard input.
func (m *Model) handleKey(key app.KeyMsg) app.UpdateResult {
	switch key.Key.Type {
	case input.CtrlC:
		return app.UpdateResult{Model: nil}

	case input.CtrlShiftC:
		if m.lastSeg != nil && m.selectedItem.FullText != "" {
			filled := formatFinalPrompt(m.selectedItem, m.varValues, true, m.lastAddonMode, m.lastAddonName)
			if err := copyToClipboard(filled); err != nil {
				m.convo.Add(ErrorSegment{Message: fmt.Sprintf("Failed to copy: %v", err)})
			} else {
				m.convo.Add(TextSegment{Text: "✓ Prompt copied to clipboard"})
			}
		}
		return app.NoCmd(m)

	case input.CtrlShiftV:
		if !m.thinking {
			text, err := pasteFromClipboard()
			if err != nil {
				m.convo.Add(ErrorSegment{Message: fmt.Sprintf("Paste failed: %v", err)})
			} else if text != "" {
				m.chatInput = m.chatInput.Paste(text)
			}
		}
		return app.NoCmd(m)

	case input.CmdC: // macOS Command+C
		if m.lastSeg != nil && m.selectedItem.FullText != "" {
			filled := formatFinalPrompt(m.selectedItem, m.varValues, true, m.lastAddonMode, m.lastAddonName)
			if err := copyToClipboard(filled); err != nil {
				m.convo.Add(ErrorSegment{Message: fmt.Sprintf("Failed to copy: %v", err)})
			} else {
				m.convo.Add(TextSegment{Text: "✓ Prompt copied to clipboard"})
			}
		}
		return app.NoCmd(m)

	case input.CmdV: // macOS Command+V
		if !m.thinking {
			text, err := pasteFromClipboard()
			if err != nil {
				m.convo.Add(ErrorSegment{Message: fmt.Sprintf("Paste failed: %v", err)})
			} else if text != "" {
				m.chatInput = m.chatInput.Paste(text)
			}
		}
		return app.NoCmd(m)

	case input.RuneKey:
		if num, ok := numKeyTypes[key.Key.Rune]; ok && m.mode == modeQuery {
			if m.awaitingFeedback && num >= 1 && num <= 5 {
				return app.WithCmd(m, func() app.Msg {
					return doSubmitFeedback(m.client, m.lastExecutionID, num, "")
				})
			}
			if m.lastSeg != nil {
				item, found := selectRecommendation(*m.lastSeg, num)
				if found {
					m.enterVarFill(item)
					return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
				}
		}
		return app.NoCmd(m)
	}
	if !m.thinking {
		oldValue := m.chatInput.Value
		m.chatInput = m.chatInput.Update(key.Key)
		// If input became empty after having content, trigger animation
		if oldValue != "" && m.chatInput.Value == "" && m.needsAnimation() {
			return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
		}
	}
	return app.NoCmd(m)

	case input.Paste:
		if !m.thinking {
			m.chatInput = m.chatInput.Paste(key.Key.Text)
		}
		return app.NoCmd(m)

	case input.Enter:
		if m.thinking {
			return app.NoCmd(m)
		}
		text, newInput := m.chatInput.Submit()
		m.chatInput = newInput
		text = strings.TrimSpace(text)
		// modeSelectConfirm: empty Enter proceeds; slash commands escape to query mode
		if m.mode == modeSelectConfirm {
			if text != "" && strings.HasPrefix(text, "/") {
				m.mode = modeQuery
				return m.handleSubmit(text)
			}
		m.proceedWithSelection()
		return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
		}
		// modeAddonDescribe: Enter (including empty) triggers addon description flow
		if m.mode == modeAddonDescribe {
			return m.handleAddonDescribe(text)
		}
		// modeAddonSelect: empty Enter skips the addon; slash commands escape to query mode
		if text == "" && m.mode != modeAddonSelect {
			return app.NoCmd(m)
		}
		if m.mode == modeAddonSelect && text != "" && strings.HasPrefix(text, "/") {
			m.mode = modeQuery
			return m.handleSubmit(text)
		}
		return m.handleSubmit(text)

	case input.ShiftEnter:
		if !m.thinking {
			m.chatInput = m.chatInput.Paste("\n")
		}
		return app.NoCmd(m)

	case input.Escape:
		if m.mode == modeSelectConfirm {
			m.mode = modeQuery
			m.spinner.SetStatus(StatusIdle, "")
			m.convo.Add(TextSegment{Text: "Selection cancelled — choose again (1-5)"})
		} else if m.mode == modeVarFill {
			m.mode = modeQuery
			m.spinner.SetStatus(StatusIdle, "")
			m.convo.Add(TextSegment{Text: "Variable fill cancelled"})
		}
		return app.NoCmd(m)

	case input.Tab:
		if m.mode == modeVarFill && m.chatInput.Value != "" {
			m.handleVarFillInput(m.chatInput.Value)
			m.chatInput = component.NewTextInput("")
		}
		return app.NoCmd(m)

	case input.MouseClick, input.MouseScrollUp, input.MouseScrollDown:
		return app.NoCmd(m)

	default:
		if !m.thinking {
			m.chatInput = m.chatInput.Update(key.Key)
		}
		return app.NoCmd(m)
	}
}

// handleSubmit processes a submitted text depending on the current mode.
func (m *Model) handleSubmit(text string) app.UpdateResult {
	switch m.mode {
	case modeQuery:
		if m.dashboardDisplayed {
			m.convo.RemoveFirst()
			m.dashboardDisplayed = false
		}
		m.convo.Add(UserMsgSegment{Text: text})

		if strings.TrimSpace(text) == "/copy" {
			if m.lastTemplateID == 0 {
				m.convo.Add(ErrorSegment{Message: "No prompt selected. Select one first (press 1-9)."})
			} else {
				filled := formatFinalPrompt(m.selectedItem, m.varValues, true, m.lastAddonMode, m.lastAddonName)
				if err := copyToClipboard(filled); err != nil {
					m.convo.Add(ErrorSegment{Message: fmt.Sprintf("Failed to copy: %v", err)})
				} else {
					m.convo.Add(TextSegment{Text: "[ok] Prompt copied to clipboard"})
				}
			}
			return app.NoCmd(m)
		}

		if strings.TrimSpace(text) == "/clean" {
			m.convo = NewTranscript()
			m.lastSeg = nil
			m.selectedItem = RecommendItem{}
			m.varValues = make(map[string]string)
			m.varFillIdx = 0
			m.lastTemplateID = 0
			m.lastExecutionID = 0
			m.availableAddons = nil
			m.mode = modeQuery
			m.chatInput = component.NewTextInput("Type a query or /help for commands...")
			m.spinner.SetStatus(StatusIdle, "")

			if m.backendOnline {
				m.needsDashboardLoad = true
				return app.UpdateResult{
					Model: m,
					Cmds: []app.Cmd{
						func() app.Msg { return doHealthCheckBg(m.client) },
					},
				}
			}
			return app.NoCmd(m)
		}

		d := dispatchCommand(text, m.client, m.topK, m.tradeoffPreference)
		switch {
		case d.msg == "__clear__":
			m.convo = NewTranscript()
			m.lastSeg = nil
			return app.NoCmd(m)
		case d.msg == "__quit__":
			return app.UpdateResult{Model: nil}
		case d.msg != "" && d.cmd == nil:
			m.convo.Add(TextSegment{Text: d.msg})
			return app.NoCmd(m)
		case d.cmd != nil:
			if strings.HasPrefix(text, "/") {
				parts := strings.Fields(text)
				switch parts[0] {
				case "/add":
					m.spinner.SetStatus(StatusIngesting, text)
				case "/add-addon":
					m.spinner.SetStatus(StatusToolCall, "add-on")
				case "/health":
					m.spinner.SetStatus(StatusToolCall, "health")
				case "/feedback":
					m.spinner.SetStatus(StatusToolCall, "feedback")
				case "/list":
					m.convo.Add(TextSegment{Text: d.msg})
					m.spinner.SetStatus(StatusToolCall, "listing...")
				}
			}
			return app.WithCmd(m, d.cmd)
		}

	case modeSelectConfirm:
		m.proceedWithSelection()
		return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })

	case modeAddonDescribe:
		return m.handleAddonDescribe(text)

	case modeAddonSelect:
		return m.handleAddonSelection(text)

	case modeVarFill:
		m.handleVarFillInput(text)
	}

	return app.NoCmd(m)
}

func (m *Model) handleRecommendResult(msg recommendResultMsg) app.UpdateResult {
	m.thinking = false
	if msg.err != nil {
		m.spinner.SetStatus(StatusError, msg.err.Error())
		m.convo.Add(ErrorSegment{Message: msg.err.Error()})
		return app.NoCmd(m)
	}
	if len(msg.resp.Results) == 0 {
		m.spinner.SetStatus(StatusComplete, "No results found")
		m.convo.Add(AssistantMsgSegment{Text: "No recommendations found."})
		return app.NoCmd(m)
	}
	m.lastFeedbackScore = 0
	m.justFoundResults = false
	items := ResultsToItems(msg.resp.Results)
	seg := RecommendSegment{Items: items, Query: m.lastQuery}
	m.lastSeg = &seg
	m.convo.Add(seg)
	if len(items) > 0 && items[0].Score > 0.7 {
		m.justFoundResults = true
	}
	m.spinner.SetStatus(StatusComplete, fmt.Sprintf("%d results", len(items)))

	if len(items) > 0 {
		m.lastTemplateID = items[0].TemplateID
	}

	latencyMs := float64(0)
	if m.timer != nil {
		latencyMs = m.timer.ElapsedMs()
	}
	return app.WithCmd(m, func() app.Msg {
		return doSubmitTelemetry(m.client, m.lastTemplateID, latencyMs, m.tradeoffPreference, m.currentModel)
	})
}

func (m *Model) handleIngestResult(msg ingestResultMsg) app.UpdateResult {
	m.thinking = false
	if msg.err != nil {
		m.spinner.SetStatus(StatusError, msg.err.Error())
		m.convo.Add(ErrorSegment{Message: msg.err.Error()})
		return app.NoCmd(m)
	}
	return m.handleIngestEnqueueResult(ingestEnqueueResultMsg{
		jobID: msg.resp.JobID,
		err:   nil,
	})
}

func (m *Model) handleIngestEnqueueResult(msg ingestEnqueueResultMsg) app.UpdateResult {
	m.thinking = false
	if msg.err != nil {
		m.spinner.SetStatus(StatusError, msg.err.Error())
		m.convo.Add(ErrorSegment{Message: msg.err.Error()})
		return app.NoCmd(m)
	}
	m.activeJobID = msg.jobID
	m.polling = true
	m.pollAttempts = 0
	m.convo.Add(IngestProgressSegment{
		JobID:  msg.jobID,
		Status: "pending",
	})
	m.spinner.SetStatus(StatusIngesting, "queued")
	return app.NoCmd(m)
}

func (m *Model) handleJobProgress(msg jobProgressMsg) app.UpdateResult {
	if msg.err != nil {
		m.polling = false
		m.activeJobID = ""
		m.spinner.SetStatus(StatusError, msg.err.Error())
		m.convo.Add(ErrorSegment{Message: fmt.Sprintf("job poll failed: %s", msg.err.Error())})
		return app.NoCmd(m)
	}
	s := msg.status
	m.pollAttempts++

	seg := IngestProgressSegment{
		JobID:          s.JobID,
		Status:         s.Status,
		ProgressPct:    s.ProgressPct,
		CurrentStep:    s.CurrentStep,
		CompletedSteps: s.CompletedSteps,
		ETASeconds:     s.ETASeconds,
		Error:          s.Error,
	}
	if s.TotalSteps != nil {
		seg.TotalSteps = *s.TotalSteps
	}
	m.convo.ReplaceLastIngestProgress(seg)

	switch s.Status {
	case "completed":
		m.polling = false
		m.activeJobID = ""
		count := 0
		if s.Result != nil {
			count = s.Result.Ingested
		}
		m.spinner.SetStatus(StatusComplete, fmt.Sprintf("%d docs ingested", count))
	case "failed":
		m.polling = false
		m.activeJobID = ""
		errMsg := "unknown error"
		if s.Error != nil {
			errMsg = *s.Error
		}
		m.spinner.SetStatus(StatusError, errMsg)
		m.convo.Add(ErrorSegment{Message: fmt.Sprintf("ingest failed: %s", errMsg)})
	default:
		if m.pollAttempts >= 120 {
			m.polling = false
			m.activeJobID = ""
			m.spinner.SetStatus(StatusError, "timed out")
			m.convo.Add(ErrorSegment{Message: "ingest job timed out after 2 minutes"})
		}
	}
	return app.NoCmd(m)
}

func (m *Model) handleAddonRegisterResult(msg addonRegisterResultMsg) app.UpdateResult {
	m.thinking = false
	if msg.err != nil {
		m.spinner.SetStatus(StatusError, msg.err.Error())
		m.convo.Add(ErrorSegment{Message: msg.err.Error()})
		return app.NoCmd(m)
	}
	m.spinner.SetStatus(StatusComplete, "Add-on registered")
	m.convo.Add(TextSegment{Text: fmt.Sprintf("[ok] Add-on registered: [%s] %s", msg.addon.Mode, msg.addon.Name)})
	return app.NoCmd(m)
}

func (m *Model) handleAddonDescribe(text string) app.UpdateResult {
	if text == "" {
		m.convo.Add(TextSegment{Text: "Skipping add-on. Using base prompt."})
		m.lastAddonMode = ""
		m.lastAddonName = ""
		m.proceedToVariableFill()
		return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
	}
	m.convo.Add(UserMsgSegment{Text: text})
	m.thinking = true
	m.spinner.SetStatus(StatusThinking, "Searching add-ons...")
	return app.WithCmd(m, func() app.Msg {
		return doRecommendAddons(m.client, text)
	})
}

func (m *Model) handleAddonRecommendResult(msg addonRecommendResultMsg) app.UpdateResult {
	m.thinking = false
	if msg.err != nil {
		m.spinner.SetStatus(StatusError, msg.err.Error())
		m.convo.Add(ErrorSegment{Message: "Add-on search failed: " + msg.err.Error()})
		m.proceedToVariableFill()
		return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
	}
	if len(msg.results) == 0 {
		m.convo.Add(TextSegment{Text: "No matching add-ons found. Using base prompt."})
		m.lastAddonMode = ""
		m.lastAddonName = ""
		m.proceedToVariableFill()
		return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
	}

	m.availableAddons = make([]api.AddOn, len(msg.results))
	for i, r := range msg.results {
		m.availableAddons[i] = api.AddOn{
			Name: r.Name, Mode: r.Mode, Suffix: r.Suffix, Description: r.Description,
		}
	}

	m.mode = modeAddonSelect
	m.addonSelectAnimFrame = 0
	m.convo.Add(TextSegment{Text: fmt.Sprintf("Found %d matching add-ons — select one or ENTER to skip:", len(msg.results))})
	for i, addon := range m.availableAddons {
		m.convo.Add(AddOnPreviewSegment{
			PromptTitle: m.selectedItem.Title,
			PromptText:  m.selectedItem.FullText,
			AddonName:   addon.Name,
			AddonMode:   addon.Mode,
			AddonSuffix: addon.Suffix,
		})
		m.convo.Add(TextSegment{Text: fmt.Sprintf("  %d. [%s] %s", i+1, addon.Mode, addon.Description)})
	}
	m.chatInput = component.NewTextInput(fmt.Sprintf("Select add-on (1-%d) or ENTER to skip...", len(m.availableAddons)))
	m.spinner.SetStatus(StatusIdle, "")
	return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
}

func (m *Model) enterVarFill(item RecommendItem) {
	m.mode = modeSelectConfirm
	m.selectedItem = item
	m.varsToFill = prompt.ParseVariables(item.FullText)
	m.varFillIdx = 0
	m.varValues = make(map[string]string)
	m.availableAddons = item.ApplicableAddons
	m.lastTemplateID = item.TemplateID
	m.selectAnimFrame = 0

	m.convo.Add(SelectionSegment{
		Title:     item.Title,
		Score:     item.Score,
		Objective: item.Objective,
		Variables: item.Variables,
	})
	m.chatInput = component.NewTextInput("Press ENTER to proceed, or ESC to reselect...")
	m.spinner.SetStatus(StatusIdle, "")
}

func (m *Model) proceedWithSelection() {
	m.mode = modeAddonDescribe
	m.addonDescribeAnimFrame = 0
	m.convo.Add(TextSegment{Text: "Describe the add-on you're looking for (or press ENTER to skip):"})
	m.convo.Add(TextSegment{Text: "  e.g. \"I want speed and less verbosity avoiding token waste\""})
	m.chatInput = component.NewTextInput("Describe desired add-on or press ENTER to skip...")
	m.spinner.SetStatus(StatusIdle, "")
}

func (m *Model) proceedToVariableFill() {
	m.mode = modeVarFill
	m.varFillAnimFrame = 0
	if len(m.varsToFill) > 0 {
		m.chatInput = component.NewTextInput("Enter value for [" + m.varsToFill[0] + "]")
	} else {
		m.showFinalPrompt()
	}
}

func (m *Model) handleAddonSelection(text string) app.UpdateResult {
	text = strings.TrimSpace(text)
	if text == "" {
		m.convo.Add(TextSegment{Text: "No add-on selected. Proceeding with base prompt."})
		m.lastAddonMode = ""
		m.lastAddonName = ""
		m.proceedToVariableFill()
		return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
	}

	idx, err := strconv.Atoi(text)
	if err != nil || idx < 1 || idx > len(m.availableAddons) {
		m.convo.Add(ErrorSegment{Message: "Invalid selection. Enter a number or press ENTER to skip."})
		return app.NoCmd(m)
	}

	selected := m.availableAddons[idx-1]
	m.lastAddonMode = selected.Mode
	m.lastAddonName = selected.Name
	m.convo.Add(TextSegment{Text: fmt.Sprintf("[ok] Selected add-on: [%s] %s", selected.Mode, selected.Description)})
	m.proceedToVariableFill()
	return app.WithCmd(m, func() app.Msg { return newAnimTickCmd() })
}

func (m *Model) handleVarFillInput(value string) {
	if m.varFillIdx >= len(m.varsToFill) {
		return
	}
	v := m.varsToFill[m.varFillIdx]
	m.varValues[v] = value
	m.varFillIdx++

	if m.varFillIdx < len(m.varsToFill) {
		next := m.varsToFill[m.varFillIdx]
		m.convo.Add(TextSegment{Text: fmt.Sprintf("Filled [%s]. Next: [%s]", v, next)})
		m.chatInput = component.NewTextInput("Enter value for [" + next + "]")
	} else {
		m.showFinalPrompt()
	}
}

func (m *Model) showFinalPrompt() {
	final := formatFinalPrompt(m.selectedItem, m.varValues, false, m.lastAddonMode, m.lastAddonName)
	m.convo.Add(AssistantMsgSegment{Text: "**Final Prompt:**\n\n" + final})

	if len(m.availableAddons) > 0 {
		m.convo.Add(TextSegment{Text: "Available addons:"})
		for _, addon := range m.availableAddons {
			m.convo.Add(TextSegment{Text: fmt.Sprintf("  [%s] %s", addon.Mode, addon.Description)})
		}
	}

	m.spinner.SetStatus(StatusComplete, "Ready")
	if m.lastSummary != nil {
		addonLabel := "none"
		if m.lastAddonMode != "" {
			addonLabel = "[" + m.lastAddonMode + "]"
		}
		m.convo.Add(SelectionAnalyticsSegment{
			TotalExecutions: m.lastSummary.TotalExecutions,
			AvgQualityScore: m.lastSummary.AvgQualityScore,
			ByCategory:      m.lastSummary.ByCategory,
			Percentages:     m.lastSummary.Percentages,
			ByModel:         m.lastSummary.ByModel,
			ModelQuality:    m.lastSummary.ModelQuality,
			AppliedAddon:    addonLabel,
			TemplateTitle:   m.selectedItem.Title,
		})
	}
	m.mode = modeQuery
	m.awaitingFeedback = true
	m.chatInput = component.NewTextInput("Type a query or /help for commands...   (press 1-5 to rate)")
	if m.timer != nil {
		m.lastLatencyMs = m.timer.ElapsedMs()
	}
}

// startRecommend begins a recommendation query, returning async cmds.
func (m *Model) startRecommend(query string) []app.Cmd {
	m.lastQuery = query
	m.timer = telemetry.NewTimer()
	m.spinner.SetStatus(StatusRecommending, "")
	m.thinking = true
	m.convo.Add(ToolCallSegment{Name: "recommend(" + truncateStr(query, 40) + ")", Closed: false})

	if !m.backendOnline {
		return []app.Cmd{func() app.Msg {
			return doSimulateResponse(query)
		}}
	}
	return []app.Cmd{func() app.Msg {
		return doRecommend(m.client, query, m.topK, m.tradeoffPreference)
	}}
}

func truncateStr(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max-3] + "..."
}

// petFace returns the ASCII face and foreground color representing current app state.
func (m *Model) petFace() (face string, color node.Color) {
	if !m.backendOnline {
		return "X _ X", colorRed
	}
	if m.spinner.Kind == StatusError {
		return "X _ X", colorRed
	}
	if m.thinking {
		return "> _ <", colMagenta
	}
	if m.lastFeedbackScore == 5 {
		return "^ _ ^", colorGreen
	}
	if m.lastFeedbackScore == 1 {
		return "T _ T", colCyan
	}
	if m.lastAddonMode == "speed" {
		return "* _ *", colCyan
	}
	if m.lastAddonMode == "quality" {
		return "• _ •", colorBlue
	}
	if m.justFoundResults {
		return "O _ O", colorGreen
	}
	if m.lastSummary != nil && m.lastSummary.AvgQualityScore > 0 && m.lastSummary.AvgQualityScore < 2.0 {
		return "¬ _ ¬", colYellow
	}
	if !m.dashboardDisplayed {
		return "- _ -", colDimGray
	}
	return "o _ o", colWhite
}

var _ = strings.Builder{}
