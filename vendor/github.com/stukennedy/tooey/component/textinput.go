package component

import (
	"strings"
	"unicode"

	"github.com/stukennedy/tooey/input"
	"github.com/stukennedy/tooey/node"
)

// TextInput holds state for a multi-line text input with cursor.
type TextInput struct {
	Value       string
	Cursor      int // rune offset into Value
	Placeholder string
	Focused     bool
}

// NewTextInput creates a text input with a placeholder.
func NewTextInput(placeholder string) TextInput {
	return TextInput{Placeholder: placeholder, Focused: true}
}

// Update handles a key event and returns the updated TextInput.
func (ti TextInput) Update(key input.Key) TextInput {
	runes := []rune(ti.Value)
	switch key.Type {
	case input.RuneKey:
		runes = append(runes[:ti.Cursor], append([]rune{key.Rune}, runes[ti.Cursor:]...)...)
		ti.Cursor++
	case input.ShiftEnter:
		runes = append(runes[:ti.Cursor], append([]rune{'\n'}, runes[ti.Cursor:]...)...)
		ti.Cursor++
	case input.Backspace:
		if ti.Cursor > 0 {
			runes = append(runes[:ti.Cursor-1], runes[ti.Cursor:]...)
			ti.Cursor--
		}
	case input.Delete:
		if ti.Cursor < len(runes) {
			runes = append(runes[:ti.Cursor], runes[ti.Cursor+1:]...)
		}
	case input.Left:
		if ti.Cursor > 0 {
			ti.Cursor--
		}
	case input.Right:
		if ti.Cursor < len(runes) {
			ti.Cursor++
		}
	case input.Home:
		// Move to start of current line
		ti.Cursor = lineStart(runes, ti.Cursor)
	case input.End:
		// Move to end of current line
		ti.Cursor = lineEnd(runes, ti.Cursor)
	case input.Up:
		ti.Cursor = moveCursorUp(runes, ti.Cursor)
	case input.Down:
		ti.Cursor = moveCursorDown(runes, ti.Cursor)
	case input.AltLeft:
		ti.Cursor = wordLeft(runes, ti.Cursor)
	case input.AltRight:
		ti.Cursor = wordRight(runes, ti.Cursor)
	}
	ti.Value = string(runes)
	return ti
}

// Paste inserts text at the cursor position in a single operation.
func (ti TextInput) Paste(text string) TextInput {
	runes := []rune(ti.Value)
	pasteRunes := []rune(text)
	newRunes := make([]rune, 0, len(runes)+len(pasteRunes))
	newRunes = append(newRunes, runes[:ti.Cursor]...)
	newRunes = append(newRunes, pasteRunes...)
	newRunes = append(newRunes, runes[ti.Cursor:]...)
	ti.Value = string(newRunes)
	ti.Cursor += len(pasteRunes)
	return ti
}

// Submit returns the current value and resets the input.
func (ti TextInput) Submit() (string, TextInput) {
	val := strings.TrimSpace(ti.Value)
	ti.Value = ""
	ti.Cursor = 0
	return val, ti
}

// LineCount returns the number of display lines.
func (ti TextInput) LineCount() int {
	if ti.Value == "" {
		return 1
	}
	return strings.Count(ti.Value, "\n") + 1
}

// Render returns a node tree displaying the multi-line input with cursor.
// If width > 0, text is word-wrapped to fit within that width.
// If width is 0, no wrapping is performed (backward compatible).
func (ti TextInput) Render(prefix string, fg, bg node.Color, width int) node.Node {
	if ti.Value == "" {
		// Show cursor block + placeholder when focused and empty
		if ti.Focused {
			return node.Row(
				node.TextStyled(prefix, fg, bg, 0),
				node.TextStyled(" ", node.Color(0), node.Color(15), 0), // block cursor
				node.TextStyled(ti.Placeholder, node.Color(8), bg, node.Dim),
			)
		}
		return node.TextStyled(prefix+ti.Placeholder, node.Color(8), bg, node.Dim)
	}

	runes := []rune(ti.Value)
	prefixWidth := len([]rune(prefix))
	contPrefix := strings.Repeat(" ", prefixWidth)

	// Split into logical lines (from newlines), then word-wrap each
	logicalLines := splitLines(string(runes))
	type displayLine struct {
		text      string
		runeStart int // rune offset in the full Value where this display line starts
	}
	var displayLines []displayLine
	runeOffset := 0
	for i, line := range logicalLines {
		lp := prefixWidth
		if i > 0 {
			lp = prefixWidth // continuation prefix same width
		}
		wrapped := wrapLine(line, width, lp)
		for _, wl := range wrapped {
			displayLines = append(displayLines, displayLine{text: wl, runeStart: runeOffset})
			runeOffset += len([]rune(wl))
		}
		runeOffset++ // account for the \n between logical lines
	}

	// Find which display line the cursor is on
	cursorDisplayLine := 0
	cursorCol := 0
	for di, dl := range displayLines {
		dlLen := len([]rune(dl.text))
		if ti.Cursor >= dl.runeStart && ti.Cursor <= dl.runeStart+dlLen {
			// Cursor is on this line (prefer earliest line if at boundary between lines)
			if ti.Cursor == dl.runeStart+dlLen && di+1 < len(displayLines) && displayLines[di+1].runeStart == ti.Cursor {
				// Cursor is at the very end of this line and start of next wrapped line;
				// place it at the start of the next line
				continue
			}
			cursorDisplayLine = di
			cursorCol = ti.Cursor - dl.runeStart
			break
		}
	}

	var lineNodes []node.Node
	for i, dl := range displayLines {
		var ln node.Node
		linePrefix := contPrefix
		if i == 0 {
			linePrefix = prefix
		}

		if i == cursorDisplayLine && ti.Focused {
			lineRunes := []rune(dl.text)
			before := string(lineRunes[:cursorCol])
			var cursorChar string
			var after string
			if cursorCol < len(lineRunes) {
				cursorChar = string(lineRunes[cursorCol])
				after = string(lineRunes[cursorCol+1:])
			} else {
				cursorChar = " "
			}
			ln = node.Row(
				node.TextStyled(linePrefix+before, fg, bg, 0),
				node.TextStyled(cursorChar, node.Color(0), node.Color(15), 0),
				node.TextStyled(after, fg, bg, 0),
			)
		} else {
			ln = node.TextStyled(linePrefix+dl.text, fg, bg, 0)
		}
		lineNodes = append(lineNodes, ln)
	}

	if len(lineNodes) == 1 {
		return lineNodes[0]
	}
	return node.Column(lineNodes...)
}

// splitLines splits on newline, always returning at least one element.
func splitLines(s string) []string {
	if s == "" {
		return []string{""}
	}
	lines := strings.Split(s, "\n")
	return lines
}

// cursorPosition converts a flat rune offset to (line, col).
func cursorPosition(runes []rune, cursor int) (int, int) {
	line, col := 0, 0
	for i := 0; i < cursor && i < len(runes); i++ {
		if runes[i] == '\n' {
			line++
			col = 0
		} else {
			col++
		}
	}
	return line, col
}

// lineStart returns the rune index of the start of the current line.
func lineStart(runes []rune, cursor int) int {
	for i := cursor - 1; i >= 0; i-- {
		if runes[i] == '\n' {
			return i + 1
		}
	}
	return 0
}

// lineEnd returns the rune index of the end of the current line.
func lineEnd(runes []rune, cursor int) int {
	for i := cursor; i < len(runes); i++ {
		if runes[i] == '\n' {
			return i
		}
	}
	return len(runes)
}

// moveCursorUp moves the cursor to the same column on the previous line.
func moveCursorUp(runes []rune, cursor int) int {
	_, col := cursorPosition(runes, cursor)
	start := lineStart(runes, cursor)
	if start == 0 {
		return 0 // already on first line
	}
	// Go to previous line
	prevLineEnd := start - 1 // the \n char
	prevLineStart := lineStart(runes, prevLineEnd)
	prevLineLen := prevLineEnd - prevLineStart
	if col > prevLineLen {
		col = prevLineLen
	}
	return prevLineStart + col
}

// moveCursorDown moves the cursor to the same column on the next line.
func moveCursorDown(runes []rune, cursor int) int {
	_, col := cursorPosition(runes, cursor)
	end := lineEnd(runes, cursor)
	if end >= len(runes) {
		return len(runes) // already on last line
	}
	// Go to next line
	nextLineStart := end + 1 // skip the \n
	nextLineEnd := lineEnd(runes, nextLineStart)
	nextLineLen := nextLineEnd - nextLineStart
	if col > nextLineLen {
		col = nextLineLen
	}
	return nextLineStart + col
}

// wordLeft moves the cursor to the start of the previous word.
func wordLeft(runes []rune, cursor int) int {
	if cursor <= 0 {
		return 0
	}
	i := cursor - 1
	// Skip whitespace/punctuation backward
	for i > 0 && !unicode.IsLetter(runes[i]) && !unicode.IsDigit(runes[i]) {
		i--
	}
	// Skip word characters backward
	for i > 0 && (unicode.IsLetter(runes[i-1]) || unicode.IsDigit(runes[i-1])) {
		i--
	}
	return i
}

// wordRight moves the cursor to the start of the next word.
func wordRight(runes []rune, cursor int) int {
	n := len(runes)
	if cursor >= n {
		return n
	}
	i := cursor
	// Skip current word characters forward
	for i < n && (unicode.IsLetter(runes[i]) || unicode.IsDigit(runes[i])) {
		i++
	}
	// Skip whitespace/punctuation forward
	for i < n && !unicode.IsLetter(runes[i]) && !unicode.IsDigit(runes[i]) {
		i++
	}
	return i
}

// wrapLine word-wraps a single line to fit within the given width.
// prefixWidth is the width consumed by the line prefix.
// If width is 0, no wrapping is performed.
func wrapLine(line string, width, prefixWidth int) []string {
	if width <= 0 {
		return []string{line}
	}
	availWidth := width - prefixWidth
	if availWidth <= 0 {
		availWidth = 1
	}

	runes := []rune(line)
	if len(runes) <= availWidth {
		return []string{line}
	}

	var result []string
	for len(runes) > 0 {
		if len(runes) <= availWidth {
			result = append(result, string(runes))
			break
		}
		// Find the last space at or before availWidth
		breakAt := -1
		for i := availWidth; i >= 0; i-- {
			if i < len(runes) && runes[i] == ' ' {
				breakAt = i
				break
			}
		}
		if breakAt <= 0 {
			// No space found — break at availWidth (mid-word as fallback)
			breakAt = availWidth
			result = append(result, string(runes[:breakAt]))
			runes = runes[breakAt:]
		} else {
			result = append(result, string(runes[:breakAt]))
			runes = runes[breakAt+1:] // skip the space
		}
	}
	return result
}
