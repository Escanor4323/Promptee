package component

import "github.com/stukennedy/tooey/node"

// StepStatus represents the state of a step.
type StepStatus int

const (
	StepPending StepStatus = iota
	StepActive
	StepDone
	StepFailed
)

// Step defines a single step in a step indicator.
type Step struct {
	Label  string
	Status StepStatus
}

var stepIcons = map[StepStatus]struct {
	icon  string
	fg    node.Color
	style node.StyleFlags
}{
	StepPending: {"○", 245, 0},
	StepActive:  {"●", 4, node.Bold},
	StepDone:    {"✓", 2, 0},
	StepFailed:  {"✗", 1, node.Bold},
}

// Steps renders a horizontal step indicator with connectors.
func Steps(steps []Step) node.Node {
	children := make([]node.Node, 0, len(steps)*2)
	for i, s := range steps {
		cfg := stepIcons[s.Status]
		children = append(children, node.Row(
			node.TextStyled(cfg.icon+" ", cfg.fg, 0, cfg.style),
			node.TextStyled(s.Label, cfg.fg, 0, cfg.style),
		))
		if i < len(steps)-1 {
			children = append(children, node.TextStyled(" → ", 245, 0, 0))
		}
	}
	return node.Row(children...)
}
