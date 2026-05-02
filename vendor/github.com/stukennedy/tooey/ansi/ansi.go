package ansi

import (
	"fmt"
	"io"

	"github.com/stukennedy/tooey/diff"
	"github.com/stukennedy/tooey/node"
)

// Render writes the minimal ANSI escape sequences for the given changes.
func Render(w io.Writer, changes []diff.Change) {
	var curFG, curBG node.Color
	var curStyle node.StyleFlags
	first := true

	for _, ch := range changes {
		// Move cursor (1-based)
		fmt.Fprintf(w, "\x1b[%d;%dH", ch.Y+1, ch.X+1)

		for _, c := range ch.Cells {
			if first || c.FG != curFG || c.BG != curBG || c.Style != curStyle {
				writeSGR(w, c.FG, c.BG, c.Style)
				curFG = c.FG
				curBG = c.BG
				curStyle = c.Style
				first = false
			}
			fmt.Fprintf(w, "%c", c.Rune)
		}
	}

	// Reset at end
	if !first {
		fmt.Fprint(w, "\x1b[0m")
	}
}

func writeSGR(w io.Writer, fg, bg node.Color, style node.StyleFlags) {
	fmt.Fprint(w, "\x1b[0")
	if style&node.Bold != 0 {
		fmt.Fprint(w, ";1")
	}
	if style&node.Dim != 0 {
		fmt.Fprint(w, ";2")
	}
	if style&node.Italic != 0 {
		fmt.Fprint(w, ";3")
	}
	if style&node.Underline != 0 {
		fmt.Fprint(w, ";4")
	}
	if style&node.Reverse != 0 {
		fmt.Fprint(w, ";7")
	}
	if fg != 0 {
		fmt.Fprintf(w, ";38;5;%d", fg)
	}
	if bg != 0 {
		fmt.Fprintf(w, ";48;5;%d", bg)
	}
	fmt.Fprint(w, "m")
}

// Terminal control sequences

func HideCursor(w io.Writer) {
	fmt.Fprint(w, "\x1b[?25l")
}

func ShowCursor(w io.Writer) {
	fmt.Fprint(w, "\x1b[?25h")
}

func ClearScreen(w io.Writer) {
	fmt.Fprint(w, "\x1b[2J")
}

func EnterAltScreen(w io.Writer) {
	fmt.Fprint(w, "\x1b[?1049h")
}

func LeaveAltScreen(w io.Writer) {
	fmt.Fprint(w, "\x1b[?1049l")
}

func MoveCursor(w io.Writer, x, y int) {
	fmt.Fprintf(w, "\x1b[%d;%dH", y+1, x+1)
}

func EnableFocusReporting(w io.Writer) {
	fmt.Fprint(w, "\x1b[?1004h")
}

func DisableFocusReporting(w io.Writer) {
	fmt.Fprint(w, "\x1b[?1004l")
}

func EnableMouseReporting(w io.Writer) {
	fmt.Fprint(w, "\x1b[?1000h\x1b[?1006h") // basic + SGR mode
}

func DisableMouseReporting(w io.Writer) {
	fmt.Fprint(w, "\x1b[?1006l\x1b[?1000l")
}

func EnableBracketedPaste(w io.Writer) {
	fmt.Fprint(w, "\x1b[?2004h")
}

func DisableBracketedPaste(w io.Writer) {
	fmt.Fprint(w, "\x1b[?2004l")
}
