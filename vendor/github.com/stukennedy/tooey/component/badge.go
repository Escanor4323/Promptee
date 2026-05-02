package component

import "github.com/stukennedy/tooey/node"

// BadgeStyle defines the visual style of a badge.
type BadgeStyle int

const (
	BadgeSuccess BadgeStyle = iota
	BadgeError
	BadgeWarning
	BadgePending
	BadgeInfo
)

var badgeConfig = map[BadgeStyle]struct {
	icon string
	fg   node.Color
}{
	BadgeSuccess: {"✓", 2},   // green
	BadgeError:   {"✗", 1},   // red
	BadgeWarning: {"●", 3},   // yellow
	BadgePending: {"○", 245}, // gray
	BadgeInfo:    {"ℹ", 4},   // blue
}

// Badge renders a status icon followed by a label.
func Badge(label string, style BadgeStyle) node.Node {
	cfg := badgeConfig[style]
	return node.Row(
		node.TextStyled(cfg.icon+" ", cfg.fg, 0, node.Bold),
		node.TextStyled(label, cfg.fg, 0, 0),
	)
}
