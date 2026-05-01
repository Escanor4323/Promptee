package tui

import (
	"strings"
	"testing"
)

func TestNewSpinnerState(t *testing.T) {
	s := NewSpinnerState()
	if s.Kind != StatusIdle {
		t.Errorf("expected StatusIdle, got %v", s.Kind)
	}
}

func TestSpinnerTick_Idle(t *testing.T) {
	s := NewSpinnerState()
	got := s.Tick()
	if got != "" {
		t.Errorf("expected empty string for idle, got %q", got)
	}
}

func TestSpinnerTick_Active(t *testing.T) {
	s := NewSpinnerState()
	s.SetStatus(StatusRecommending, "")
	got := s.Tick()
	if !strings.Contains(got, ">>>") {
		t.Errorf("expected >>> prefix, got %q", got)
	}
	if !strings.Contains(got, "Cogitating") && !strings.Contains(got, "Pontificating") {
		t.Errorf("expected cogitating message, got %q", got)
	}
}

func TestSpinnerTick_Complete(t *testing.T) {
	s := NewSpinnerState()
	s.SetStatus(StatusComplete, "5 results")
	got := s.Tick()
	if !strings.Contains(got, "[ok]") {
		t.Errorf("expected [ok] prefix, got %q", got)
	}
	if !strings.Contains(got, "5 results") {
		t.Errorf("expected detail '5 results', got %q", got)
	}
}

func TestSpinnerTick_Error(t *testing.T) {
	s := NewSpinnerState()
	s.SetStatus(StatusError, "connection refused")
	got := s.Tick()
	if !strings.Contains(got, "[!]") {
		t.Errorf("expected [!] prefix, got %q", got)
	}
	if !strings.Contains(got, "connection refused") {
		t.Errorf("expected error detail, got %q", got)
	}
}

func TestSpinnerSetStatus_ResetsIndex(t *testing.T) {
	s := NewSpinnerState()
	s.SetStatus(StatusRecommending, "")
	s.Tick()
	s.Tick()
	if s.Index == 0 {
		t.Error("expected index to advance after ticks")
	}
	s.SetStatus(StatusIngesting, "")
	if s.Index != 0 {
		t.Errorf("expected index reset on kind change, got %d", s.Index)
	}
}

func TestSpinnerSetStatus_SameKindKeepsIndex(t *testing.T) {
	s := NewSpinnerState()
	s.SetStatus(StatusRecommending, "")
	s.Tick()
	s.Tick()
	idx := s.Index
	s.SetStatus(StatusRecommending, "new detail")
	if s.Index != idx {
		t.Errorf("expected index preserved on same kind, got %d want %d", s.Index, idx)
	}
}

func TestCogitatingMessagesNotEmpty(t *testing.T) {
	if len(CogitatingMessages) == 0 {
		t.Error("CogitatingMessages should not be empty")
	}
}

func TestStatusPrefixMap(t *testing.T) {
	kinds := []StatusKind{StatusThinking, StatusToolCall, StatusRecommending, StatusIngesting, StatusError, StatusComplete}
	for _, k := range kinds {
		if _, ok := statusPrefix[k]; !ok {
			t.Errorf("missing prefix for %v", k)
		}
	}
}

func TestStatusLabelMap(t *testing.T) {
	kinds := []StatusKind{StatusThinking, StatusToolCall, StatusRecommending, StatusIngesting, StatusError, StatusComplete}
	for _, k := range kinds {
		if _, ok := statusLabel[k]; !ok {
			t.Errorf("missing label for %v", k)
		}
	}
}
