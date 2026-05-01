package telemetry

import (
	"testing"
	"time"
)

func TestNewTimer(t *testing.T) {
	timer := NewTimer()
	if timer == nil {
		t.Fatal("expected non-nil timer")
	}
	if timer.start.IsZero() {
		t.Error("expected start time to be set")
	}
}

func TestTimerElapsedMs(t *testing.T) {
	timer := NewTimer()
	elapsed := timer.ElapsedMs()
	if elapsed < 0 {
		t.Errorf("elapsed should be non-negative, got %f", elapsed)
	}
}

func TestNewCollector(t *testing.T) {
	c := NewCollector()
	if c == nil {
		t.Fatal("expected non-nil collector")
	}
	if len(c.events) != 0 {
		t.Error("expected empty collector")
	}
}

func TestCollectorRecord(t *testing.T) {
	c := NewCollector()
	ts := time.Now().Unix()
	c.Record("test_event", ts, map[string]string{"key": "value"})

	if len(c.events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(c.events))
	}
	if c.events[0].Name != "test_event" {
		t.Errorf("expected name 'test_event', got %q", c.events[0].Name)
	}
	if c.events[0].Payload["key"] != "value" {
		t.Errorf("expected payload key=value, got %v", c.events[0].Payload)
	}
}

func TestCollectorFlush(t *testing.T) {
	c := NewCollector()
	c.Record("e1", 1, nil)
	c.Record("e2", 2, nil)

	events := c.Flush()
	if len(events) != 2 {
		t.Fatalf("expected 2 events, got %d", len(events))
	}
	if events[0].Name != "e1" || events[1].Name != "e2" {
		t.Errorf("unexpected event order: %v", events)
	}

	// After flush, internal buffer should be empty
	events2 := c.Flush()
	if len(events2) != 0 {
		t.Errorf("expected empty flush after reset, got %d events", len(events2))
	}
}

func TestCollectorFlushReturnsCopy(t *testing.T) {
	c := NewCollector()
	c.Record("e1", 1, nil)

	events1 := c.Flush()
	events2 := c.Flush()

	if len(events1) != 1 {
		t.Fatalf("first flush: expected 1 event, got %d", len(events1))
	}
	if len(events2) != 0 {
		t.Errorf("second flush: expected 0 events, got %d", len(events2))
	}
}

func TestEstimateTokens(t *testing.T) {
	tests := []struct {
		name               string
		input              string
		output             string
		wantInputTokens    int
		wantOutputTokens   int
		wantContextPctHigh bool // true means pct > 0
	}{
		{
			name:             "empty strings",
			input:            "",
			output:           "",
			wantInputTokens:  0,
			wantOutputTokens: 0,
		},
		{
			name:               "four chars is one token each",
			input:              "abcd",
			output:             "efgh",
			wantInputTokens:    1,
			wantOutputTokens:   1,
			wantContextPctHigh: true,
		},
		{
			name:               "truncating integer division",
			input:              "abc",   // 3 chars → 0 tokens
			output:             "abcde", // 5 chars → 1 token
			wantInputTokens:    0,
			wantOutputTokens:   1,
			wantContextPctHigh: true,
		},
		{
			name:               "non-zero context window pct",
			input:              "this is a somewhat longer input sentence for testing",
			output:             "short out",
			wantInputTokens:    13,
			wantOutputTokens:   2,
			wantContextPctHigh: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			inTok, outTok, pct := EstimateTokens(tc.input, tc.output)
			if inTok != tc.wantInputTokens {
				t.Errorf("inputTokens: want %d, got %d", tc.wantInputTokens, inTok)
			}
			if outTok != tc.wantOutputTokens {
				t.Errorf("outputTokens: want %d, got %d", tc.wantOutputTokens, outTok)
			}
			if tc.wantContextPctHigh && pct <= 0 {
				t.Errorf("contextWindowPct: want > 0, got %f", pct)
			}
			if !tc.wantContextPctHigh && pct != 0 {
				t.Errorf("contextWindowPct: want 0, got %f", pct)
			}
		})
	}
}

func TestEstimateTokensContextWindowFormula(t *testing.T) {
	// 200_000 chars input → 50_000 input tokens = 25% of 200k window
	input := make([]byte, 200_000)
	inTok, outTok, pct := EstimateTokens(string(input), "")
	if inTok != 50_000 {
		t.Errorf("want 50000 input tokens, got %d", inTok)
	}
	if outTok != 0 {
		t.Errorf("want 0 output tokens, got %d", outTok)
	}
	if pct < 24.9 || pct > 25.1 {
		t.Errorf("want context pct ~25, got %f", pct)
	}
}
