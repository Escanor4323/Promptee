package component

import (
	"time"

	"github.com/stukennedy/tooey/app"
	"github.com/stukennedy/tooey/node"
)

// SpinnerStyle selects the animation frame set.
type SpinnerStyle int

const (
	SpinnerDots SpinnerStyle = iota
	SpinnerLine
	SpinnerBraille
)

var spinnerFrameSets = map[SpinnerStyle][]string{
	SpinnerDots:    {"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"},
	SpinnerLine:    {"-", "\\", "|", "/"},
	SpinnerBraille: {"⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"},
}

// SpinnerFrames returns the frame strings for a given spinner style.
func SpinnerFrames(style SpinnerStyle) []string {
	return spinnerFrameSets[style]
}

// Spinner renders a spinner frame with a label.
func Spinner(label string, frameIdx int, style SpinnerStyle, fg node.Color) node.Node {
	frames := spinnerFrameSets[style]
	frame := frames[frameIdx%len(frames)]
	return node.Row(
		node.TextStyled(frame+" ", fg, 0, node.Bold),
		node.Text(label),
	)
}

// SpinnerTickMsg is sent when a spinner tick fires.
type SpinnerTickMsg struct{}

// SpinnerTick returns a Cmd that sends a SpinnerTickMsg after the given interval.
func SpinnerTick(interval time.Duration) app.Cmd {
	return func() app.Msg {
		time.Sleep(interval)
		return SpinnerTickMsg{}
	}
}
