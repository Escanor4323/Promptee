package tui

import "github.com/stukennedy/tooey/node"

// Maude-style 256-color palette (matches ~/TUI/tooey-repo/demos/maude).
const (
	colWhite    node.Color = 15
	colGray     node.Color = 245
	colDimGray  node.Color = 240
	colDarkGray node.Color = 236
	colBrGreen  node.Color = 10
	colYellow   node.Color = 3
	colMagenta  node.Color = 5
	colCyan     node.Color = 6
	colOrange   node.Color = 208
)

// Semantic aliases used across the package.
const (
	colorPink       node.Color = 205
	colorDefault    node.Color = 0
	colorCodeBG     node.Color = 236
	colorRed        node.Color = 196
	colorGreen      node.Color = 10
	colorBlue       node.Color = 6
	colorBrightBlue node.Color = 6
	colorOrange     node.Color = 208
	colorDarkGray   node.Color = 245
	colorMagenta    node.Color = 5
	colorYellow     node.Color = 3
	colorCyan       node.Color = 6
	colorLightGray  node.Color = 254
	colorMidGray    node.Color = 244
)

var statusPrefixColors = map[StatusKind]node.Color{
	StatusThinking:     colorBlue,
	StatusToolCall:     colorBlue,
	StatusRecommending: colorBlue,
	StatusIngesting:    colorOrange,
	StatusError:        colorRed,
	StatusComplete:     colorGreen,
}
