package tui

import (
	"strings"
	"testing"

	"github.com/user/promptee/internal/api"
)

func TestThinkingSegment_Render(t *testing.T) {
	s := ThinkingSegment{Text: "hello world"}
	got := s.Render()
	if !strings.Contains(got, "> Thinking") {
		t.Error("expected thinking prefix")
	}
	if !strings.Contains(got, "hello world") {
		t.Error("expected text content")
	}
}

func TestThinkingSegment_Render_Truncated(t *testing.T) {
	long := strings.Repeat("x", 600)
	s := ThinkingSegment{Text: long}
	got := s.Render()
	if !strings.Contains(got, "...") {
		t.Error("expected truncation marker")
	}
}

func TestTextSegment_Render(t *testing.T) {
	s := TextSegment{Text: "some output"}
	if s.Render() != "some output" {
		t.Errorf("expected 'some output', got %q", s.Render())
	}
}

func TestToolCallSegment_Render(t *testing.T) {
	s := ToolCallSegment{Name: "recommend"}
	got := s.Render()
	if !strings.Contains(got, ">>") {
		t.Error("expected >> prefix")
	}
	if !strings.Contains(got, "recommend") {
		t.Error("expected tool name")
	}
}

func TestToolResultSegment_Render(t *testing.T) {
	s := ToolResultSegment{Name: "bash", Content: "ok", IsError: false}
	got := s.Render()
	if !strings.Contains(got, ">>") {
		t.Error("expected >> prefix")
	}
	if !strings.Contains(got, "Tool result") {
		t.Error("expected 'Tool result' label")
	}
}

func TestToolResultSegment_Render_Error(t *testing.T) {
	s := ToolResultSegment{Name: "bash", Content: "failed", IsError: true}
	got := s.Render()
	if !strings.Contains(got, "Tool error") {
		t.Error("expected 'Tool error' label")
	}
}

func TestToolResultSegment_Render_Truncated(t *testing.T) {
	s := ToolResultSegment{Name: "bash", Content: strings.Repeat("y", 900), IsError: false}
	got := s.Render()
	if !strings.Contains(got, "...") {
		t.Error("expected truncation marker for long content")
	}
}

func TestRecommendSegment_Render(t *testing.T) {
	items := []RecommendItem{
		{Index: 1, Title: "Write API", Score: 0.92, Variables: []string{"LANG"}},
		{Index: 2, Title: "Debug code", Score: 0.87, Variables: nil},
	}
	s := RecommendSegment{Items: items, Query: "test"}
	got := s.Render()
	if !strings.Contains(got, ">>>") {
		t.Error("expected >>> prefix")
	}
	if !strings.Contains(got, "0.92") {
		t.Error("expected score in output")
	}
	if !strings.Contains(got, "Write API") {
		t.Error("expected title in output")
	}
}

func TestErrorSegment_Render(t *testing.T) {
	s := ErrorSegment{Message: "timeout"}
	got := s.Render()
	if !strings.Contains(got, "[!]") {
		t.Error("expected [!] prefix")
	}
	if !strings.Contains(got, "timeout") {
		t.Error("expected error message")
	}
}

func TestRecommendItem_Render(t *testing.T) {
	i := RecommendItem{Index: 1, Title: "Test", Score: 0.95, Variables: []string{"A", "B"}}
	got := i.Render()
	if !strings.Contains(got, "0.95") {
		t.Error("expected score")
	}
	if !strings.Contains(got, "A, B") {
		t.Error("expected variables")
	}
}

func TestRecommendItem_Render_NoVars(t *testing.T) {
	i := RecommendItem{Index: 3, Title: "NoVars", Score: 0.5, Variables: nil}
	got := i.Render()
	if strings.Contains(got, "Variables:") {
		t.Error("should not show variables section when empty")
	}
}

func TestTranscript_Add(t *testing.T) {
	tr := NewTranscript()
	tr.Add(TextSegment{Text: "hello"})
	tr.Add(ErrorSegment{Message: "err"})
	if len(tr.Segments()) != 3 {
		t.Errorf("expected 3 segments (splash art + hello + err), got %d", len(tr.Segments()))
	}
}

func TestTranscript_Render(t *testing.T) {
	tr := NewTranscript()
	tr.Add(TextSegment{Text: "first"})
	tr.Add(TextSegment{Text: "second"})
	got := tr.Render()
	if !strings.Contains(got, "first") || !strings.Contains(got, "second") {
		t.Error("expected both segments in render")
	}
}

func TestTranscript_Render_Truncation(t *testing.T) {
	tr := NewTranscript()
	tr.charLimit = 50
	for i := 0; i < 20; i++ {
		tr.Add(TextSegment{Text: "segment content here that is long"})
	}
	got := tr.Render()
	if len(got) > 50 {
		t.Errorf("expected render under charLimit, got %d chars", len(got))
	}
	if !strings.Contains(got, "truncated") {
		t.Error("expected truncation marker")
	}
}

func TestResultsToItems(t *testing.T) {
	results := []api.RecommendResult{
		{ID: 1, Title: "A", HybridScore: 0.9, Variables: []string{"X"}, FullText: "text"},
		{ID: 2, Title: "B", HybridScore: 0.8, Variables: nil, FullText: "text2"},
	}
	items := ResultsToItems(results)
	if len(items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(items))
	}
	if items[0].Index != 1 || items[0].Title != "A" {
		t.Errorf("unexpected first item: %+v", items[0])
	}
	if items[1].Index != 2 || items[1].Title != "B" {
		t.Errorf("unexpected second item: %+v", items[1])
	}
}
