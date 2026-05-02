package tui

import (
	"fmt"
	"os/exec"
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
	modeVarFill
	modeAddOnSelect
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
	thinking                 bool
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
	}
}

// TooeyApp returns an app.App wired to this model's Init/Update/View.
func TooeyApp(apiURL string, topK int, tradeoffPreference string) *app.App {
	mdl := NewModel(apiURL, topK, tradeoffPreference)
	mdl.needsInitialHealthCheck = true
	mdl.needsDashboardLoad = true
	return &app.App{
		Init: func() interface{} {
			mdl.width, mdl.height = input.TermSize()
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

	case recommendResultMsg:
		return m.handleRecommendResult(msg)

	case ingestResultMsg:
		return m.handleIngestResult(msg)

	case healthResultMsg:
		m.backendOnline = msg.err == nil
		if m.needsDashboardLoad {
			m.needsDashboardLoad = false
			if m.backendOnline {
				if msg.explicit {
					m.convo.Add(TextSegment{Text: "[ok] Backend online"})
				} else {
					m.convo.Add(TextSegment{Text: " Loading dashboard..."})
				}
				return app.WithCmd(m, func() app.Msg {
					return doGetTelemetrySummary(m.client)
				})
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
			m.convo.Add(TextSegment{Text: "[ok] Feedback recorded"})
		}
		return app.NoCmd(m)

	case telemetrySummaryResultMsg:
		m.convo.RemoveFirst()
		if msg.resp != nil {
			m.convo.Add(DashboardSegment{
				TotalExecutions: msg.resp.TotalExecutions,
				AvgQualityScore: msg.resp.AvgQualityScore,
				ByCategory:      msg.resp.ByCategory,
				Percentages:     msg.resp.Percentages,
			})
		} else if msg.err != nil {
			m.convo.Add(TextSegment{Text: "[!] Dashboard: " + msg.err.Error()})
		} else {
			m.convo.Add(TextSegment{Text: "[!] Dashboard: No data available"})
		}
		m.convo.Add(TextSegment{Text: ""})
		m.convo.Add(SplashArtSegment{Text: splashArt})
		m.convo.Add(TextSegment{Text: " Promptee — Local MLOps & RAG CLI (Codename: Daedalus)"})
		m.convo.Add(TextSegment{Text: ""})
		m.dashboardDisplayed = true
		return app.NoCmd(m)

	case tickMsg:
		if m.spinner.Kind != StatusIdle && m.spinner.Kind != StatusComplete {
			m.spinner.Tick()
		}
		m.healthCheckCounter++
		if m.healthCheckCounter >= 5 {
			m.healthCheckCounter = 0
			return app.UpdateResult{
				Model: m,
				Cmds: []app.Cmd{
					func() app.Msg { return doHealthCheckBg(m.client) },
					newTickCmd,
				},
			}
		}
		return app.WithCmd(m, newTickCmd)
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
			filled := formatFinalPrompt(m.selectedItem, m.varValues)
			if err := copyToClipboard(filled); err != nil {
				m.convo.Add(ErrorSegment{Message: fmt.Sprintf("Failed to copy: %v", err)})
			} else {
				m.convo.Add(TextSegment{Text: "✓ Prompt copied to clipboard"})
			}
		}
		return app.NoCmd(m)

	case input.CtrlShiftV:
		if !m.thinking {
			// Try to read from clipboard and paste into input
			cmd := exec.Command("pbpaste")
			output, err := cmd.Output()
			if err == nil {
				m.chatInput.Value += string(output)
			}
		}
		return app.NoCmd(m)

	case input.RuneKey:
		if num, ok := numKeyTypes[key.Key.Rune]; ok && m.mode == modeQuery && m.lastSeg != nil {
			item, found := selectRecommendation(*m.lastSeg, num)
			if found {
				m.enterVarFill(item)
			}
			return app.NoCmd(m)
		}
		if !m.thinking {
			m.chatInput = m.chatInput.Update(key.Key)
		}
		return app.NoCmd(m)

	case input.Paste:
		if !m.thinking {
			m.chatInput.Value += key.Key.Text
		}
		return app.NoCmd(m)

	case input.Enter:
		if m.thinking {
			return app.NoCmd(m)
		}
		text, newInput := m.chatInput.Submit()
		m.chatInput = newInput
		text = strings.TrimSpace(text)
		if text == "" {
			return app.NoCmd(m)
		}
		return m.handleSubmit(text)

	case input.ShiftEnter:
		if !m.thinking {
			m.chatInput.Value += "\n"
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
				filled := formatFinalPrompt(m.selectedItem, m.varValues)
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
				return app.WithCmd(m, func() app.Msg {
					return doGetTelemetrySummary(m.client)
				})
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
				case "/ingest":
					m.spinner.SetStatus(StatusIngesting, text)
				case "/health":
					m.spinner.SetStatus(StatusToolCall, "health")
				case "/feedback":
					m.spinner.SetStatus(StatusToolCall, "feedback")
				}
			}
			return app.WithCmd(m, d.cmd)
		}

	case modeSelectConfirm:
		m.proceedWithSelection()

	case modeAddonSelect:
		m.handleAddonSelection(text)

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
	items := ResultsToItems(msg.resp.Results)
	seg := RecommendSegment{Items: items, Query: m.lastQuery}
	m.lastSeg = &seg
	m.convo.Add(seg)
	m.spinner.SetStatus(StatusComplete, fmt.Sprintf("%d results", len(items)))

	if len(items) > 0 {
		m.lastTemplateID = items[0].TemplateID
	}

	latencyMs := float64(0)
	if m.timer != nil {
		latencyMs = m.timer.ElapsedMs()
	}
	return app.WithCmd(m, func() app.Msg {
		return doSubmitTelemetry(m.client, m.lastTemplateID, latencyMs, m.tradeoffPreference)
	})
}

func (m *Model) handleIngestResult(msg ingestResultMsg) app.UpdateResult {
	m.thinking = false
	if msg.err != nil {
		m.spinner.SetStatus(StatusError, msg.err.Error())
		m.convo.Add(ErrorSegment{Message: msg.err.Error()})
		return app.NoCmd(m)
	}
	m.spinner.SetStatus(StatusComplete, fmt.Sprintf("Ingested %d chunks", msg.resp.Ingested))
	m.convo.Add(TextSegment{Text: fmt.Sprintf("[ok] Ingested %d chunks", msg.resp.Ingested)})
	return app.NoCmd(m)
}

func (m *Model) enterVarFill(item RecommendItem) {
	m.mode = modeSelectConfirm
	m.selectedItem = item
	m.varsToFill = prompt.ParseVariables(item.FullText)
	m.varFillIdx = 0
	m.varValues = make(map[string]string)
	m.availableAddons = item.ApplicableAddons
	m.lastTemplateID = item.TemplateID

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
	if len(m.availableAddons) > 0 {
		m.mode = modeAddonSelect
		m.convo.Add(TextSegment{Text: "Available Add-Ons (optional enhancements for SPEED/COST/QUALITY):"})
		for i, addon := range m.availableAddons {
			m.convo.Add(TextSegment{Text: fmt.Sprintf("  %d. [%s] %s", i+1, addon.Mode, addon.Description)})
		}
		m.chatInput = component.NewTextInput("Select addon (1-" + fmt.Sprintf("%d", len(m.availableAddons)) + ") or press ENTER to skip...")
		m.spinner.SetStatus(StatusIdle, "")
	} else {
		m.proceedToVariableFill()
	}
}

func (m *Model) proceedToVariableFill() {
	m.mode = modeVarFill
	if len(m.varsToFill) > 0 {
		m.chatInput = component.NewTextInput("Enter value for [" + m.varsToFill[0] + "]")
	} else {
		m.showFinalPrompt()
	}
}

func (m *Model) handleAddonSelection(text string) {
	text = strings.TrimSpace(text)
	if text == "" {
		m.convo.Add(TextSegment{Text: "No add-on selected. Proceeding with base prompt."})
		m.lastAddonMode = ""
		m.proceedToVariableFill()
		return
	}

	idx, err := strconv.Atoi(text)
	if err != nil || idx < 1 || idx > len(m.availableAddons) {
		m.convo.Add(ErrorSegment{Message: "Invalid selection. Enter a number or press ENTER to skip."})
		return
	}

	selected := m.availableAddons[idx-1]
	m.lastAddonMode = selected.Mode
	m.convo.Add(TextSegment{Text: fmt.Sprintf("[ok] Selected add-on: [%s] %s", selected.Mode, selected.Description)})
	m.proceedToVariableFill()
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
	final := formatFinalPrompt(m.selectedItem, m.varValues)
	m.convo.Add(AssistantMsgSegment{Text: "**Final Prompt:**\n\n" + final})

	if len(m.availableAddons) > 0 {
		m.convo.Add(TextSegment{Text: "Available addons:"})
		for _, addon := range m.availableAddons {
			m.convo.Add(TextSegment{Text: fmt.Sprintf("  [%s] %s", addon.Mode, addon.Description)})
		}
	}

	m.spinner.SetStatus(StatusComplete, "Ready")
	m.mode = modeQuery
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

var _ = strings.Builder{}
