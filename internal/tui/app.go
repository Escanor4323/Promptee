package tui

import (
	"fmt"
	"strings"

	"github.com/stukennedy/tooey/app"
	"github.com/stukennedy/tooey/component"
	"github.com/stukennedy/tooey/input"
	"github.com/stukennedy/tooey/node"
	"github.com/user/promptee/internal/api"
	"github.com/user/promptee/internal/prompt"
	"github.com/user/promptee/internal/telemetry"
)

type inputMode int

const (
	modeQuery inputMode = iota
	modeVarFill
	modeAddOnSelect
)

// Model holds all application state for the tooey-based TUI.
type Model struct {
	client     *api.Client
	chatInput  component.TextInput
	convo      *Transcript
	spinner    SpinnerState
	timer      *telemetry.Timer
	scrollOff  int

	mode          inputMode
	width         int
	height        int
	backendOnline bool
	lastQuery     string
	topK               int
	tradeoffPreference string
	lastSeg       *RecommendSegment
	healthCheckCounter int
	needsInitialHealthCheck bool

	selectedItem   RecommendItem
	varsToFill     []string
	varFillIdx     int
	varValues      map[string]string
	availableAddons []api.AddOn
	lastLatencyMs  float64
	thinking       bool
}

// NewModel creates the initial application model.
func NewModel(apiURL string, topK int, tradeoffPreference string) *Model {
	return &Model{
		client:    api.NewClient(apiURL),
		chatInput: component.NewTextInput("Type a query or /help for commands..."),
		convo:     NewTranscript(),
		spinner:   NewSpinnerState(),
		topK:               topK,
		tradeoffPreference: tradeoffPreference,
		mode:      modeQuery,
		varValues: make(map[string]string),
	}
}

// TooeyApp returns an app.App wired to this model's Init/Update/View.
func TooeyApp(apiURL string, topK int, tradeoffPreference string) *app.App {
	mdl := NewModel(apiURL, topK, tradeoffPreference)
	mdl.needsInitialHealthCheck = true
	return &app.App{
		Init: func() interface{} {
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
		return app.WithCmd(m, func() app.Msg {
			return doHealthCheckBg(m.client)
		})
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
		if msg.explicit {
			if m.backendOnline {
				m.convo.Add(TextSegment{Text: "[ok] Backend online"})
			} else {
				m.convo.Add(ErrorSegment{Message: "Backend offline -- run /daemon start or ./promptee daemon start"})
			}
		}
		return app.NoCmd(m)

	case simulateResponseMsg:
		m.convo.Add(AssistantMsgSegment{Text: "Backend offline. Simulated response for: " + msg.query})
		m.spinner.SetStatus(StatusComplete, "Simulated")
		m.thinking = false
		return app.NoCmd(m)

	case telemetryResultMsg:
		if msg.err == nil {
			m.convo.Add(TextSegment{Text: "[ok] Telemetry recorded"})
		}
		return app.NoCmd(m)

	case feedbackResultMsg:
		if msg.err != nil {
			m.convo.Add(ErrorSegment{Message: msg.err.Error()})
		} else {
			m.convo.Add(TextSegment{Text: "[ok] Feedback recorded"})
		}
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
		if m.mode == modeVarFill {
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
		m.convo.Add(UserMsgSegment{Text: text})
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
	return app.WithCmd(m, func() app.Msg {
		return doSubmitTelemetry(m.client, 0, m.timer.ElapsedMs())
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
	m.mode = modeVarFill
	m.selectedItem = item
	m.varsToFill = prompt.ParseVariables(item.FullText)
	m.varFillIdx = 0
	m.varValues = make(map[string]string)
	m.availableAddons = nil

	if len(m.varsToFill) > 0 {
		m.chatInput = component.NewTextInput("Enter value for [" + m.varsToFill[0] + "]")
		m.spinner.SetStatus(StatusIdle, "")
	} else {
		m.showFinalPrompt()
	}
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
	m.convo.Add(TextSegment{Text: "[ok] Final Prompt:\n\n" + final})
	m.spinner.SetStatus(StatusComplete, "Copied to clipboard")
	m.mode = modeQuery
	m.chatInput = component.NewTextInput("Type a query or /help for commands...")
	m.lastLatencyMs = m.timer.ElapsedMs()
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
