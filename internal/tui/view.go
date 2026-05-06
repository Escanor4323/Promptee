package tui

import (
	"fmt"
	"strings"

	"github.com/stukennedy/tooey/node"
)

// view builds the full node tree matching the maude reference design.
func (m *Model) view(focused string) node.Node {
	w := m.width
	if w < 10 {
		w = 80
	}

	// Top status bar with pet face in the middle.
	face, faceColor := m.petFace()
	petStr := " " + face + " "
	right := m.statusRight()
	pad := w - len(" Promptee") - len(petStr) - len(right)
	if pad < 1 {
		pad = 1
	}
	statusBar := node.Row(
		node.TextStyled(" Promptee", colWhite, colDarkGray, node.Bold),
		node.TextStyled(petStr, faceColor, node.Color(238), node.Bold),
		node.TextStyled(strings.Repeat(" ", pad), colWhite, colDarkGray, 0),
		node.TextStyled(right, colWhite, colDarkGray, node.Bold),
	)

	sep := node.TextStyled(strings.Repeat("─", w), colDimGray, colorDefault, 0)

	// Conversation area — append thinking indicator when active.
	chatNodes := m.convo.NodeRender()
	if m.thinking {
		chatNodes = append(chatNodes,
			node.Text(""),
			node.TextStyled("  ● Thinking...", colMagenta, colorDefault, node.Bold),
		)
	}
	convoArea := node.Column(chatNodes...).
		WithFlex(1).
		WithScrollToBottom().
		WithScrollOffset(m.scrollOff).
		WithKey("convo")

	var inputLine node.Node
	if highlighted, ok := renderCommandInput(m.chatInput.Value); ok {
		inputLine = highlighted
	} else if m.mode == modeSelectConfirm && m.chatInput.Value == "" {
		inputLine = renderAnimatedInput("  ❯ ", "Press ENTER to proceed, or ESC to reselect...", m.selectAnimFrame, false)
	} else if m.mode == modeQuery && m.chatInput.Value == "" {
		inputLine = renderAnimatedInput("  ❯ ", "Type a query...", m.queryAnimFrame, false)
	} else if m.mode == modeAddonSelect && m.chatInput.Value == "" {
		inputLine = renderAnimatedInput("  ❯ ", m.chatInput.Placeholder, m.addonSelectAnimFrame, false)
	} else if m.mode == modeAddonOrder && m.chatInput.Value == "" {
		inputLine = renderAnimatedInput("  ❯ ", m.chatInput.Placeholder, m.addonOrderAnimFrame, false)
	} else if m.mode == modeAddonPreview && m.chatInput.Value == "" {
		inputLine = renderAnimatedInput("  ❯ ", m.chatInput.Placeholder, m.addonPreviewAnimFrame, false)
	} else if m.mode == modeAddonQuery && m.chatInput.Value == "" {
		inputLine = renderAnimatedInput("  ❯ ", m.chatInput.Placeholder, m.addonQueryAnimFrame, false)
	} else if m.mode == modeVarFill && m.chatInput.Value == "" {
		inputLine = renderAnimatedInput("  ❯ ", m.chatInput.Placeholder, m.varFillAnimFrame, false)
	} else {
		inputLine = m.chatInput.Render("  ❯ ", colWhite, colorDefault, 0)
	}

	// Bottom border
	bottomBorder := node.TextStyled(strings.Repeat("─", w), colDimGray, colorDefault, 0)

	// Help bar with key hints and active mode tag.
	helpText := "Ctrl+C:quit │ /help:commands │ 1-9:pick prompt or add-on │ mouse:scroll"
	if m.mode == modeVarFill {
		helpText += " │ [var-fill]"
	} else if m.mode == modeAddonQuery {
		helpText += " │ [addon-query]"
	} else if m.mode == modeAddonSelect {
		helpText += " │ [addon-select]"
	} else if m.mode == modeAddonOrder {
		helpText += " │ [addon-order]"
	} else if m.mode == modeAddonPreview {
		helpText += " │ [addon-preview]"
	}
	helpPad := w - len(helpText)
	if helpPad < 0 {
		helpPad = 0
	}
	helpBar := node.TextStyled(helpText+strings.Repeat(" ", helpPad), colGray, colDarkGray, 0)

	return node.Column(
		statusBar,
		sep,
		convoArea,
		sep,
		inputLine.WithKey("chat-input").WithFocusable(),
		bottomBorder,
		helpBar,
	)
}

// statusRight builds the right portion of the top status bar.
func (m *Model) statusRight() string {
	backend := "offline"
	if m.backendOnline {
		backend = "online"
	}
	return fmt.Sprintf("backend:%s │ k:%d │ model:%s ", backend, m.topK, m.currentModel)
}

// renderCommandInput colorizes a /command input line.
// The command name (after /) is rendered in cyan; arguments in orange.
// Returns (node, true) when text starts with '/', otherwise (zero, false).
func renderCommandInput(text string) (node.Node, bool) {
	if !strings.HasPrefix(text, "/") {
		return node.Node{}, false
	}
	parts := strings.SplitN(text, " ", 2)
	cmdPart := parts[0]
	children := []node.Node{
		node.TextStyled("  > ", colWhite, colorDefault, 0),
		node.TextStyled(cmdPart, colCyan, colorDefault, node.Bold),
	}
	if len(parts) == 2 && parts[1] != "" {
		children = append(children,
			node.Text(" "),
			node.TextStyled(parts[1], colOrange, colorDefault, 0),
		)
	}
	return node.Row(children...), true
}

// renderAnimatedInput renders a placeholder with oscillating brightness wave animation.
// The wave moves left-to-right then right-to-left (ping-pong pattern).
func renderAnimatedInput(prefix, placeholder string, frame int, done bool) node.Node {
	runes := []rune(placeholder)
	n := len(runes)

	// Calculate oscillating position: 0,1,2,...,n-1,n-2,...,1,0,1,2,...
	var brightPos int
	if n <= 1 {
		brightPos = 0
	} else {
		cycleLen := 2 * (n - 1)
		posInCycle := frame % cycleLen
		if posInCycle < n {
			brightPos = posInCycle
		} else {
			brightPos = cycleLen - posInCycle
		}
	}

	prefixNode := node.TextStyled(prefix, colWhite, colorDefault, 0)
	if done {
		return node.Row(prefixNode, node.TextStyled(placeholder, colGray, colorDefault, 0))
	}
	children := []node.Node{prefixNode}
	for i, ch := range runes {
		d := i - brightPos
		if d < 0 {
			d = -d
		}
		var col node.Color
		switch {
		case d == 0:
			col = node.Color(255)
		case d == 1:
			col = node.Color(253)
		case d == 2:
			col = node.Color(249)
		case d == 3:
			col = node.Color(245)
		case d <= 5:
			col = node.Color(241)
		default:
			col = node.Color(238)
		}
		children = append(children, node.TextStyled(string(ch), col, colorDefault, 0))
	}
	return node.Row(children...)
}
