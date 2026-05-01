package tui

import (
	"fmt"
	"time"
)

var CogitatingMessages = []string{
	"Cogitating...",
	"Pontificating...",
	"Ruminating...",
	"Deliberating...",
	"Pondering...",
	"Meditating...",
	"Percolating...",
	"Marinating...",
}

type StatusKind string

const (
	StatusThinking     StatusKind = "thinking"
	StatusToolCall     StatusKind = "tool_call"
	StatusRecommending StatusKind = "recommending"
	StatusIngesting    StatusKind = "ingesting"
	StatusError        StatusKind = "error"
	StatusComplete     StatusKind = "complete"
	StatusIdle         StatusKind = "idle"
)

var statusPrefix = map[StatusKind]string{
	StatusThinking:     ">",
	StatusToolCall:     ">>",
	StatusRecommending: ">>>",
	StatusIngesting:    ">>",
	StatusError:        "[!]",
	StatusComplete:     "[ok]",
	StatusIdle:         "",
}

var statusLabel = map[StatusKind]string{
	StatusThinking:     "Thinking",
	StatusToolCall:     "Tool call",
	StatusRecommending: "Recommending",
	StatusIngesting:    "Ingesting",
	StatusError:        "Error",
	StatusComplete:     "Done",
	StatusIdle:         "",
}

type SpinnerState struct {
	Index    int
	Kind     StatusKind
	Detail   string
	LastTick time.Time
	prevKind StatusKind
}

func NewSpinnerState() SpinnerState {
	return SpinnerState{Kind: StatusIdle}
}

func (s *SpinnerState) Tick() string {
	if s.Kind == StatusIdle {
		return ""
	}

	prefix := statusPrefix[s.Kind]
	label := statusLabel[s.Kind]

	coloredPrefix := prefix

	if s.Kind == StatusComplete || s.Kind == StatusError {
		if s.Detail != "" {
			return coloredPrefix + " " + label + ": " + s.Detail
		}
		return coloredPrefix + " " + label
	}

	msg := CogitatingMessages[s.Index]
	result := fmt.Sprintf("%s %s", coloredPrefix, msg)
	s.Index = (s.Index + 1) % len(CogitatingMessages)
	s.LastTick = time.Now()
	return result
}

func (s *SpinnerState) SetStatus(kind StatusKind, detail string) {
	if kind != s.prevKind {
		s.Index = 0
	}
	s.Kind = kind
	s.Detail = detail
	s.prevKind = kind
}
