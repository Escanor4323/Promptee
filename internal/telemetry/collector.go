package telemetry

import "time"

// Timer tracks execution duration.
type Timer struct {
	start time.Time
}

// NewTimer creates and starts a new timer.
func NewTimer() *Timer {
	return &Timer{start: time.Now()}
}

// ElapsedMs returns the elapsed time in milliseconds since the timer started.
func (t *Timer) ElapsedMs() float64 {
	return float64(time.Since(t.start).Milliseconds())
}

// Collector accumulates telemetry events for batch reporting.
type Collector struct {
	events []Event
}

// Event represents a single telemetry data point.
type Event struct {
	Name      string
	Timestamp int64
	Payload   map[string]string
}

// NewCollector creates a new telemetry collector.
func NewCollector() *Collector {
	return &Collector{events: make([]Event, 0)}
}

// Record appends a telemetry event.
func (c *Collector) Record(name string, timestamp int64, payload map[string]string) {
	c.events = append(c.events, Event{Name: name, Timestamp: timestamp, Payload: payload})
}

// Flush returns all collected events and resets the internal buffer.
func (c *Collector) Flush() []Event {
	events := make([]Event, len(c.events))
	copy(events, c.events)
	c.events = c.events[:0]
	return events
}

// contextWindowTokens is the assumed context window size used for percentage calculations.
const contextWindowTokens = 200_000

// EstimateTokens estimates token counts for input and output text using a
// simple heuristic of 1 token per 4 characters, and returns the combined
// usage as a percentage of the assumed context window.
func EstimateTokens(inputText, outputText string) (inputTokens, outputTokens int, contextWindowPct float64) {
	inputTokens = len(inputText) / 4
	outputTokens = len(outputText) / 4
	contextWindowPct = float64(inputTokens+outputTokens) / contextWindowTokens * 100
	return inputTokens, outputTokens, contextWindowPct
}
