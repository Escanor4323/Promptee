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

	// Top status bar: " Promptee" left, backend/mode info right.
	left := " Promptee"
	right := m.statusRight()
	pad := w - len(left) - len(right)
	if pad < 1 {
		pad = 1
	}
	statusBar := node.TextStyled(left+strings.Repeat(" ", pad)+right, colWhite, colDarkGray, node.Bold)

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
	} else {
		inputLine = m.chatInput.Render("  > ", colWhite, colorDefault, 0)
	}

	// Bottom border
	bottomBorder := node.TextStyled(strings.Repeat("─", w), colDimGray, colorDefault, 0)

	// Help bar with key hints and active mode tag.
	helpText := "Ctrl+C:quit │ /help:commands │ 1-9:select │ mouse:scroll"
	if m.mode == modeVarFill {
		helpText += " │ [var-fill]"
	} else if m.mode == modeAddOnSelect {
		helpText += " │ [addon-select]"
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
	return fmt.Sprintf("backend:%s │ k:%d ", backend, m.topK)
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
