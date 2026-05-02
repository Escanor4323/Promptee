package tui

import (
	"fmt"
	"strings"

	"github.com/stukennedy/tooey/node"
	"github.com/user/promptee/internal/api"
)

// Segment is a piece of conversation content. Implementations provide
// both Render() for string output and NodeRender() for tooey node trees.
type Segment interface {
	Render() string
}

// --- Segment types with both Render and NodeRender ---

type ThinkingSegment struct {
	Text string
}

func (s ThinkingSegment) Render() string {
	raw := s.Text
	if len(raw) > 500 {
		raw = "..." + raw[len(raw)-497:]
	}
	return "> Thinking\n " + raw
}

func (s ThinkingSegment) NodeRender() node.Node {
	raw := s.Text
	if len(raw) > 500 {
		raw = "..." + raw[len(raw)-497:]
	}
	return node.Column(
		node.TextStyled("> Thinking", colorBlue, colorDefault, node.Bold),
		node.Text("  "+raw),
	)
}

type TextSegment struct {
	Text string
}

func (s TextSegment) Render() string {
	return s.Text
}

func (s TextSegment) NodeRender() node.Node {
	return node.Paragraph(s.Text, colorDefault, colorDefault, 0)
}

type SplashArtSegment struct {
	Text string
}

func (s SplashArtSegment) Render() string {
	return s.Text
}

func (s SplashArtSegment) NodeRender() node.Node {
	lines := strings.Split(strings.TrimSpace(s.Text), "\n")
	var rows []node.Node
	for _, line := range lines {
		children := []node.Node{}
		for _, ch := range line {
			if ch == '$' {
				children = append(children, node.TextStyled("$", colOrange, colorDefault, 0))
			} else {
				children = append(children, node.Text(string(ch)))
			}
		}
		rows = append(rows, node.Row(children...))
	}
	return node.Column(rows...)
}

type ToolCallSegment struct {
	Name   string
	Closed bool
}

func (s ToolCallSegment) Render() string {
	return ">> Tool call: " + s.Name
}

func (s ToolCallSegment) NodeRender() node.Node {
	return node.TextStyled("  ▸ "+s.Name, colorCyan, colorDefault, node.Bold)
}

type ToolResultSegment struct {
	Name    string
	Content string
	IsError bool
}

func (s ToolResultSegment) Render() string {
	label := "Tool result"
	if s.IsError {
		label = "Tool error"
	}
	raw := s.Content
	if len(raw) > 800 {
		raw = "..." + raw[len(raw)-797:]
	}
	return fmt.Sprintf(">> %s: %s\n %s", label, s.Name, raw)
}

func (s ToolResultSegment) NodeRender() node.Node {
	label := "Tool result"
	labelColor := colorDefault
	if s.IsError {
		label = "Tool error"
		labelColor = colorRed
	}
	raw := s.Content
	if len(raw) > 800 {
		raw = "..." + raw[len(raw)-797:]
	}
	inner := node.Column(
		node.TextStyled(fmt.Sprintf(">> %s: %s", label, s.Name), labelColor, colorDefault, node.Bold),
		node.Indent(2, node.Text(raw)),
	)
	return node.Box(node.BorderRounded, inner)
}

type RecommendSegment struct {
	Items []RecommendItem
	Query string
}

func (s RecommendSegment) Render() string {
	var b strings.Builder
	b.WriteString(">>> Recommendations:\n")
	for i, item := range s.Items {
		if i > 0 {
			b.WriteString(" ─────────────────────────────────────────────────────────\n")
		}
		b.WriteString(item.Render())
		b.WriteByte('\n')
	}
	return b.String()
}

func (s RecommendSegment) NodeRender() node.Node {
	children := []node.Node{
		node.TextStyled(">>>  Recommendations:", colorBlue, colorDefault, node.Bold),
	}
	for i, item := range s.Items {
		if i > 0 {
			children = append(children, node.TextStyled(" ─────────────────────────────────────────────────────────", colDimGray, colorDefault, 0))
		}
		children = append(children, item.NodeRender())
	}
	return node.Column(children...)
}

type RecommendItem struct {
	Index            int
	TemplateID       int
	Title            string
	Score            float64
	Objective        string
	Variables        []string
	FullText         string
	ApplicableAddons []api.AddOn
}

func (i RecommendItem) Render() string {
	vars := ""
	if len(i.Variables) > 0 {
		vars = " Variables: " + strings.Join(i.Variables, ", ")
	}
	return fmt.Sprintf(" %d. [%.2f] %s%s", i.Index, i.Score, i.Title, vars)
}

func (i RecommendItem) NodeRender() node.Node {
	vars := ""
	if len(i.Variables) > 0 {
		vars = " Variables: " + strings.Join(i.Variables, ", ")
	}
	scoreText := fmt.Sprintf("[%.2f]", i.Score)
	return node.Row(
		node.TextStyled(fmt.Sprintf(" %d. ", i.Index), colorPink, colorDefault, node.Bold),
		node.TextStyled(scoreText, colorOrange, colorDefault, 0),
		node.Text(" "+i.Title+vars),
	)
}

type ErrorSegment struct {
	Message string
}

func (s ErrorSegment) Render() string {
	return "[!] Error: " + s.Message
}

func (s ErrorSegment) NodeRender() node.Node {
	return node.Row(
		node.TextStyled("[!]", colorRed, colorDefault, node.Bold),
		node.TextStyled(" Error: "+s.Message, colorRed, colorDefault, 0),
	)
}

type SelectionSegment struct {
	Title    string
	Score    float64
	Objective string
	Variables []string
}

func (s SelectionSegment) Render() string {
	vars := ""
	if len(s.Variables) > 0 {
		vars = "\nVariables: " + strings.Join(s.Variables, ", ")
	}
	return fmt.Sprintf(">>> SELECTED: %s [%.2f]\n%s%s\n(press ESC to reselect)", s.Title, s.Score, s.Objective, vars)
}

func (s SelectionSegment) NodeRender() node.Node {
	scoreText := fmt.Sprintf("[%.2f]", s.Score)
	children := []node.Node{
		node.Row(
			node.TextStyled(">>> SELECTED: ", colorGreen, colorDefault, node.Bold),
			node.TextStyled(s.Title, colorOrange, colorDefault, node.Bold),
			node.TextStyled(" "+scoreText, colorOrange, colorDefault, 0),
		),
		node.Text(s.Objective),
	}
	if len(s.Variables) > 0 {
		children = append(children, node.Text("Variables: "+strings.Join(s.Variables, ", ")))
	}
	children = append(children, node.TextStyled("(press ESC to reselect)", colGray, colorDefault, 0))
	return node.Column(children...)
}

type DashboardSegment struct {
	TotalExecutions  int
	AvgQualityScore  float64
	ByCategory       map[string]int
	Percentages      map[string]float64
}

func (s DashboardSegment) Render() string {
	if s.ByCategory == nil {
		s.ByCategory = make(map[string]int)
	}
	if s.Percentages == nil {
		s.Percentages = make(map[string]float64)
	}
	var b strings.Builder
	b.WriteString(">>> Usage Dashboard\n")
	b.WriteString(fmt.Sprintf(" Total executions: %d\n", s.TotalExecutions))
	b.WriteString(fmt.Sprintf(" Avg quality: %.2f\n", s.AvgQualityScore))
	b.WriteString(" By category:\n")
	for _, cat := range []string{"speed", "cost", "quality", "balanced"} {
		count := s.ByCategory[cat]
		pct := s.Percentages[cat]
		b.WriteString(fmt.Sprintf("  %s: %d (%.1f%%)\n", cat, count, pct))
	}
	return b.String()
}

func (s DashboardSegment) NodeRender() node.Node {
	if s.ByCategory == nil {
		s.ByCategory = make(map[string]int)
	}
	if s.Percentages == nil {
		s.Percentages = make(map[string]float64)
	}
	children := []node.Node{
		node.TextStyled(">>> Usage Dashboard", colorBlue, colorDefault, node.Bold),
		node.Text(fmt.Sprintf(" Total executions: %d", s.TotalExecutions)),
		node.Text(fmt.Sprintf(" Avg quality: %.2f", s.AvgQualityScore)),
		node.Text(" By category:"),
	}
	for _, cat := range []string{"speed", "cost", "quality", "balanced"} {
		count := s.ByCategory[cat]
		pct := s.Percentages[cat]
		children = append(children, node.Text(fmt.Sprintf("  %s: %d (%.1f%%)", cat, count, pct)))
	}
	return node.Column(children...)
}

type UserMsgSegment struct {
	Text string
}

func (s UserMsgSegment) Render() string {
	return "❯ " + s.Text
}

func (s UserMsgSegment) NodeRender() node.Node {
	lines := strings.Split(s.Text, "\n")
	children := make([]node.Node, 0, len(lines))
	for i, line := range lines {
		prefix := "    "
		if i == 0 {
			prefix = "  ❯ "
		}
		children = append(children, node.TextStyled(prefix+line, colDimGray, colorDefault, 0))
	}
	if len(children) == 1 {
		return children[0]
	}
	return node.Column(children...)
}

type AssistantMsgSegment struct {
	Text string
}

func (s AssistantMsgSegment) Render() string {
	return s.Text
}

func (s AssistantMsgSegment) NodeRender() node.Node {
	nodes := renderMarkdownLines(s.Text)
	return node.Column(nodes...)
}

// ToolUseBlockSegment shows a tool execution. While IsRunning is true it
// renders as a one-line label; once complete it renders a box with the
// result summary.
type ToolUseBlockSegment struct {
	Name      string
	Args      string
	IsRunning bool
	Result    string
	IsError   bool
}

func (s ToolUseBlockSegment) Render() string {
	call := s.Name
	if s.Args != "" {
		a := s.Args
		if len(a) > 40 {
			a = a[:37] + "..."
		}
		call += "(" + a + ")"
	}

	if s.IsRunning {
		return " >> " + call
	}

	result := s.Result
	if len(result) > 68 {
		result = result[:65] + "..."
	}

	prefix := "[ok]"
	if s.IsError {
		prefix = "[!]"
	}

	inner := node.Column(
		node.Text(call),
		node.Text(result),
	)
	_ = inner

	return prefix + " " + call + " → " + result
}

func (s ToolUseBlockSegment) NodeRender() node.Node {
	call := s.Name
	if s.Args != "" {
		a := s.Args
		if len(a) > 40 {
			a = a[:37] + "..."
		}
		call += "(" + a + ")"
	}

	if s.IsRunning {
		return node.TextStyled("  ▸ "+call, colorCyan, colorDefault, node.Bold)
	}

	result := s.Result
	if len(result) > 68 {
		result = result[:65] + "..."
	}

	icon, fg := toolIconColor(s.Name)
	title := node.TextStyled("  "+icon+call, fg, colorDefault, node.Bold)
	content := node.TextStyled("    "+result, colGray, colorDefault, 0)
	return node.Box(node.BorderRounded, node.Column(title, content))
}

// --- Transcript ---

type Transcript struct {
	segments  []Segment
	charLimit int
}

func NewTranscript() *Transcript {
	t := &Transcript{charLimit: 10000}
	return t
}

func (t *Transcript) Add(s Segment) {
	t.segments = append(t.segments, s)
}

func (t *Transcript) Segments() []Segment {
	out := make([]Segment, len(t.segments))
	copy(out, t.segments)
	return out
}

func (t *Transcript) RemoveFirst() {
	if len(t.segments) > 0 {
		t.segments = t.segments[1:]
	}
}

func (t *Transcript) Render() string {
	return t.renderWithLimit(t.charLimit)
}

// NodeRender produces a slice of node.Nodes for the conversation area.
// A blank spacer is prepended before each segment, matching the maude layout.
func (t *Transcript) NodeRender() []node.Node {
	nodes := make([]node.Node, 0, len(t.segments)*2)
	for _, seg := range t.segments {
		if nr, ok := seg.(interface{ NodeRender() node.Node }); ok {
			nodes = append(nodes, node.Text(""))
			nodes = append(nodes, nr.NodeRender())
		}
	}
	return nodes
}

func (t *Transcript) renderWithLimit(limit int) string {
	var rendered []string
	for _, seg := range t.segments {
		out := seg.Render()
		if out != "" {
			rendered = append(rendered, out)
		}
	}

	candidate := strings.Join(rendered, "\n\n")
	if len(candidate) <= limit {
		return candidate
	}

	truncMarker := "... (truncated)\n"
	for len(rendered) > 1 {
		rendered = rendered[1:]
		candidate = truncMarker + strings.Join(rendered, "\n\n")
		if len(candidate) <= limit {
			return candidate
		}
	}

	if len(rendered) > 0 {
		tail := rendered[0]
		budget := limit - len(truncMarker)
		if budget > 20 && len(tail) > budget {
			tail = "..." + tail[len(tail)-budget+3:]
		}
		return truncMarker + tail
	}

	return ""
}

// ReplaceLastToolUse swaps the most recent ToolUseBlockSegment in-place so
// the running placeholder can be replaced with the completed result box.
func (t *Transcript) ReplaceLastToolUse(s ToolUseBlockSegment) bool {
	for i := len(t.segments) - 1; i >= 0; i-- {
		if _, ok := t.segments[i].(ToolUseBlockSegment); ok {
			t.segments[i] = s
			return true
		}
	}
	return false
}

// --- Markdown rendering (ported from maude reference design) ---

func renderMarkdownLines(text string) []node.Node {
	var nodes []node.Node
	for _, line := range strings.Split(text, "\n") {
		nodes = append(nodes, renderMarkdownLine(line))
	}
	return nodes
}

func renderMarkdownLine(line string) node.Node {
	trimmed := strings.TrimLeft(line, " ")
	indent := len(line) - len(trimmed)
	pad := "  " + strings.Repeat(" ", indent)

	if strings.HasPrefix(trimmed, "- [x] ") || strings.HasPrefix(trimmed, "- [X] ") {
		return node.Row(
			node.TextStyled(pad+"✔  ", colBrGreen, colorDefault, 0),
			node.TextStyled(trimmed[6:], colWhite, colorDefault, 0),
		)
	}
	if strings.HasPrefix(trimmed, "- [ ] ") {
		return node.Row(
			node.TextStyled(pad+"☐  ", colGray, colorDefault, 0),
			node.TextStyled(trimmed[6:], colGray, colorDefault, node.Dim),
		)
	}
	if strings.HasPrefix(trimmed, "- ") {
		return node.Row(
			node.TextStyled(pad+"•  ", colorCyan, colorDefault, 0),
			node.TextStyled(trimmed[2:], colWhite, colorDefault, 0),
		)
	}
	if len(trimmed) >= 3 && trimmed[0] >= '0' && trimmed[0] <= '9' {
		if dot := strings.Index(trimmed, ". "); dot > 0 && dot <= 3 {
			return node.Row(
				node.TextStyled(pad+trimmed[:dot+1]+"  ", colorCyan, colorDefault, 0),
				node.TextStyled(trimmed[dot+2:], colWhite, colorDefault, 0),
			)
		}
	}
	if trimmed == "" {
		return node.Text("")
	}
	return node.TextStyled(pad+trimmed, colWhite, colorDefault, 0)
}

// toolIconColor returns the icon and foreground color for a tool block title.
func toolIconColor(name string) (string, node.Color) {
	switch {
	case strings.HasPrefix(name, "Read"), strings.HasPrefix(name, "Grep"), strings.HasPrefix(name, "Glob"):
		return "▸ ", colorCyan
	case strings.HasPrefix(name, "Edit"), strings.HasPrefix(name, "Write"):
		return "▸ ", colorYellow
	case strings.HasPrefix(name, "Bash"), strings.HasPrefix(name, "Shell"):
		return "▸ ", colorOrange
	default:
		return "▸ ", colGray
	}
}

func ResultsToItems(results []api.RecommendResult) []RecommendItem {
	items := make([]RecommendItem, len(results))
	for i, r := range results {
		items[i] = RecommendItem{
			Index:            i + 1,
			TemplateID:       r.TemplateID,
			Title:            r.Title,
			Score:            r.HybridScore,
			Objective:        r.Objective,
			Variables:        r.Variables,
			FullText:         r.FullText,
			ApplicableAddons: r.ApplicableAddons,
		}
	}
	return items
}
