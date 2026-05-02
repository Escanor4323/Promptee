package input

import (
	"context"
	"io"
	"os"
	"os/signal"
	"syscall"
	"time"

	"golang.org/x/term"
)

// Ensure syscall is used for SIGWINCH
var _ = syscall.SIGWINCH

// KeyType identifies the kind of key event.
type KeyType int

const (
	RuneKey KeyType = iota
	Up
	Down
	Left
	Right
	Tab
	ShiftTab
	Enter
	Escape
	Backspace
	Delete
	Home
	End
	PageUp
	PageDown
	CtrlC
	CtrlD
	CtrlZ
	ShiftEnter
	FocusIn
	FocusOut
	MouseClick
	MouseScrollUp
	MouseScrollDown
	AltLeft
	AltRight
	AltUp
	AltDown
	Paste // Bracketed paste — Key.Rune is unused; full text is in Key.Text
	CtrlShiftC
	CtrlShiftV
)

// Key represents a keyboard input event.
type Key struct {
	Type KeyType
	Rune rune
	Text string // used for Paste events to carry the full pasted text
}

// ResizeMsg indicates the terminal was resized.
type ResizeMsg struct {
	Width, Height int
}

// escTimeout is how long to wait after receiving a lone ESC byte before
// deciding it's a bare Escape press rather than the start of a CSI sequence.
const escTimeout = 50 * time.Millisecond

type readResult struct {
	data []byte
	err  error
}

// ReadKeys reads raw terminal input and sends parsed Key events.
// It uses a timeout to disambiguate bare Escape from ESC-prefixed sequences.
func ReadKeys(ctx context.Context, r io.Reader) <-chan Key {
	ch := make(chan Key, 32)

	// Raw byte reader goroutine — feeds chunks into rawCh
	rawCh := make(chan readResult, 4)
	go func() {
		defer close(rawCh)
		buf := make([]byte, 4096)
		for {
			n, err := r.Read(buf)
			if n > 0 {
				data := make([]byte, n)
				copy(data, buf[:n])
				rawCh <- readResult{data: data}
			}
			if err != nil {
				rawCh <- readResult{err: err}
				return
			}
		}
	}()

	// Key parser goroutine — reads from rawCh, handles ESC disambiguation
	go func() {
		defer close(ch)

		var pasteBuf []byte // non-nil when inside a bracketed paste

		for {
			select {
			case <-ctx.Done():
				return
			case rr, ok := <-rawCh:
				if !ok || rr.err != nil {
					return
				}
				data := rr.data

				// If we're inside a paste, buffer data until we find the end marker
				if pasteBuf != nil {
					pasteBuf = append(pasteBuf, data...)
					end := indexBytes(pasteBuf, pasteEnd)
					if end < 0 {
						continue // keep buffering
					}
					text := string(pasteBuf[:end])
					if !send(ch, ctx, Key{Type: Paste, Text: text}) {
						return
					}
					// Process any data after the paste end marker
					remainder := pasteBuf[end+len(pasteEnd):]
					pasteBuf = nil
					if len(remainder) > 0 {
						for _, k := range parseInput(remainder) {
							if !send(ch, ctx, k) {
								return
							}
						}
					}
					continue
				}

				// Check if data ends with a lone ESC byte
				if data[len(data)-1] == 0x1b {
					// Parse everything before the trailing ESC
					if len(data) > 1 {
						for _, k := range parseInput(data[:len(data)-1]) {
							if !send(ch, ctx, k) {
								return
							}
						}
					}
					// Wait briefly: is this bare Escape or start of a CSI?
					select {
					case <-ctx.Done():
						return
					case rr2, ok := <-rawCh:
						if !ok || rr2.err != nil {
							// No more data — it was bare Escape
							send(ch, ctx, Key{Type: Escape})
							return
						}
						// Got follow-up data — check if it continues an escape sequence
						if rr2.data[0] == '[' {
							// Combine ESC + new data as a single escape sequence
							combined := make([]byte, 1+len(rr2.data))
							combined[0] = 0x1b
							copy(combined[1:], rr2.data)
							for _, k := range parseInput(combined) {
								if !send(ch, ctx, k) {
									return
								}
							}
						} else {
							// Not a CSI continuation — emit Escape, then parse new data
							if !send(ch, ctx, Key{Type: Escape}) {
								return
							}
							for _, k := range parseInput(rr2.data) {
								if !send(ch, ctx, k) {
									return
								}
							}
						}
					case <-time.After(escTimeout):
						// Timeout — bare Escape
						if !send(ch, ctx, Key{Type: Escape}) {
							return
						}
					}
					continue
				}

				// Check if data contains a paste start with no end marker
				// (parseInput handles complete pastes internally)
				pasteIdx := indexBytes(data, pasteStart)
				if pasteIdx >= 0 {
					// Parse any keys before the paste start
					if pasteIdx > 0 {
						for _, k := range parseInput(data[:pasteIdx]) {
							if !send(ch, ctx, k) {
								return
							}
						}
					}
					// Check if the complete paste is in this buffer
					after := data[pasteIdx+len(pasteStart):]
					endIdx := indexBytes(after, pasteEnd)
					if endIdx >= 0 {
						// Complete paste in this buffer — parseInput handles it
						for _, k := range parseInput(data[pasteIdx:]) {
							if !send(ch, ctx, k) {
								return
							}
						}
					} else {
						// Partial paste — start buffering from after the start marker
						pasteBuf = append([]byte{}, after...)
					}
					continue
				}

				// Normal case: parse all bytes
				for _, k := range parseInput(data) {
					if !send(ch, ctx, k) {
						return
					}
				}
			}
		}
	}()

	return ch
}

func send(ch chan<- Key, ctx context.Context, k Key) bool {
	select {
	case ch <- k:
		return true
	case <-ctx.Done():
		return false
	}
}

// WatchResize listens for SIGWINCH and sends ResizeMsg events.
func WatchResize(ctx context.Context) <-chan ResizeMsg {
	ch := make(chan ResizeMsg, 4)
	sigCh := make(chan os.Signal, 4)
	signal.Notify(sigCh, syscall.SIGWINCH)
	go func() {
		defer close(ch)
		defer signal.Stop(sigCh)
		for {
			select {
			case <-ctx.Done():
				return
			case <-sigCh:
				w, h := TermSize()
				select {
				case ch <- ResizeMsg{Width: w, Height: h}:
				case <-ctx.Done():
					return
				}
			}
		}
	}()
	return ch
}

// TermSize returns the current terminal width and height.
func TermSize() (int, int) {
	w, h, err := term.GetSize(int(os.Stdout.Fd()))
	if err != nil {
		return 80, 24
	}
	return w, h
}

// pasteStart is the bracketed paste mode start marker.
var pasteStart = []byte{0x1b, '[', '2', '0', '0', '~'}

// pasteEnd is the bracketed paste mode end marker.
var pasteEnd = []byte{0x1b, '[', '2', '0', '1', '~'}

// parseInput parses raw bytes into Key events.
func parseInput(data []byte) []Key {
	var keys []Key
	i := 0
	for i < len(data) {
		// Check for bracketed paste start (complete paste within this buffer)
		if hasPrefixAt(data, i, pasteStart) {
			start := i + len(pasteStart)
			end := indexBytes(data[start:], pasteEnd)
			if end >= 0 {
				text := string(data[start : start+end])
				keys = append(keys, Key{Type: Paste, Text: text})
				i = start + end + len(pasteEnd)
				continue
			}
			// No end marker found — this is a partial paste that spans reads.
			// Skip remaining bytes; ReadKeys handles cross-read buffering.
			return keys
		}

		if data[i] == 0x1b { // ESC
			if i+1 < len(data) && data[i+1] == '[' {
				// CSI sequence
				k, consumed := parseCSI(data[i+2:])
				if consumed > 0 {
					keys = append(keys, k)
					i += 2 + consumed
					continue
				}
				// Unrecognized CSI — skip the entire sequence rather than
				// emitting a bare Escape. CSI sequences end with a byte
				// in the range 0x40-0x7E (the "final byte").
				skipped := skipCSI(data[i+2:])
				if skipped > 0 {
					i += 2 + skipped
					continue
				}
			}
			// Alt+Enter (ESC followed by CR or LF) → ShiftEnter
			if i+1 < len(data) && (data[i+1] == '\r' || data[i+1] == '\n') {
				keys = append(keys, Key{Type: ShiftEnter})
				i += 2
				continue
			}
			keys = append(keys, Key{Type: Escape})
			i++
		} else if data[i] == '\r' {
			keys = append(keys, Key{Type: Enter})
			i++
		} else if data[i] == '\n' {
			// Ctrl+J or literal newline → newline insertion
			keys = append(keys, Key{Type: ShiftEnter})
			i++
		} else if data[i] == '\t' {
			keys = append(keys, Key{Type: Tab})
			i++
		} else if data[i] == 0x7f || data[i] == '\b' {
			keys = append(keys, Key{Type: Backspace})
			i++
		} else if data[i] == 0x03 { // Ctrl+C
			keys = append(keys, Key{Type: CtrlC})
			i++
		} else if data[i] == 0x04 { // Ctrl+D
			keys = append(keys, Key{Type: CtrlD})
			i++
		} else if data[i] == 0x1a { // Ctrl+Z
			keys = append(keys, Key{Type: CtrlZ})
			i++
		} else if data[i] >= 0x20 { // printable or multi-byte UTF-8
			r, size := decodeRune(data[i:])
			keys = append(keys, Key{Type: RuneKey, Rune: r})
			i += size
		} else {
			i++ // skip unknown control chars
		}
	}
	return keys
}

func parseCSI(data []byte) (Key, int) {
	if len(data) == 0 {
		return Key{}, 0
	}
	switch data[0] {
	case 'A':
		return Key{Type: Up}, 1
	case 'B':
		return Key{Type: Down}, 1
	case 'C':
		return Key{Type: Right}, 1
	case 'D':
		return Key{Type: Left}, 1
	case 'H':
		return Key{Type: Home}, 1
	case 'F':
		return Key{Type: End}, 1
	case 'Z':
		return Key{Type: ShiftTab}, 1
	case 'I':
		return Key{Type: FocusIn}, 1
	case 'O':
		return Key{Type: FocusOut}, 1
	}
	// Handle modifier sequences like \x1b[1;3D (Alt+Left), \x1b[1;3C (Alt+Right)
	if len(data) >= 4 && data[0] == '1' && data[1] == ';' && data[2] == '3' {
		switch data[3] {
		case 'A':
			return Key{Type: AltUp}, 4
		case 'B':
			return Key{Type: AltDown}, 4
		case 'C':
			return Key{Type: AltRight}, 4
		case 'D':
			return Key{Type: AltLeft}, 4
		}
	}
	// Handle Ctrl+Shift sequences: \x1b[67;6u (Ctrl+Shift+C), \x1b[86;6u (Ctrl+Shift+V)
	if len(data) >= 5 && (string(data[0:3]) == "67;" || string(data[0:3]) == "86;") && (data[3] == '6' || data[3] == '1') && data[4] == 'u' {
		if data[0] == '6' && data[1] == '7' { // 67 = 'C'
			return Key{Type: CtrlShiftC}, 5
		}
		if data[0] == '8' && data[1] == '6' { // 86 = 'V'
			return Key{Type: CtrlShiftV}, 5
		}
	}
	// Handle sequences like \x1b[5~ (PageUp), \x1b[6~ (PageDown), \x1b[3~ (Delete)
	if len(data) >= 2 && data[1] == '~' {
		switch data[0] {
		case '3':
			return Key{Type: Delete}, 2
		case '5':
			return Key{Type: PageUp}, 2
		case '6':
			return Key{Type: PageDown}, 2
		}
	}
	// Kitty keyboard protocol: \x1b[13;2u = Shift+Enter
	if len(data) >= 4 && data[0] == '1' && data[1] == '3' && data[2] == ';' && data[3] == '2' {
		if len(data) >= 5 && data[4] == 'u' {
			return Key{Type: ShiftEnter}, 5
		}
	}
	// SGR mouse: \x1b[<btn;x;yM or \x1b[<btn;x;ym
	if len(data) >= 1 && data[0] == '<' {
		for j := 1; j < len(data); j++ {
			if data[j] == 'M' || data[j] == 'm' {
				btn := parseSGRButton(data[1:j])
				kt := MouseClick
				switch btn {
				case 64:
					kt = MouseScrollUp
				case 65:
					kt = MouseScrollDown
				}
				return Key{Type: kt}, j + 1
			}
		}
	}
	// Normal mouse: \x1b[M + 3 bytes (btn, x, y)
	if len(data) >= 1 && data[0] == 'M' && len(data) >= 4 {
		btn := data[1] - 32
		kt := MouseClick
		switch btn {
		case 64:
			kt = MouseScrollUp
		case 65:
			kt = MouseScrollDown
		}
		return Key{Type: kt}, 4
	}
	return Key{}, 0
}

// skipCSI finds the end of an unrecognized CSI sequence and returns how many
// bytes to skip (after the ESC[). CSI parameter bytes are in 0x30-0x3F,
// intermediate bytes in 0x20-0x2F, and the final byte in 0x40-0x7E.
func skipCSI(data []byte) int {
	for j := 0; j < len(data); j++ {
		b := data[j]
		if b >= 0x40 && b <= 0x7E {
			return j + 1 // include the final byte
		}
	}
	return 0 // no final byte found — incomplete sequence
}

// parseSGRButton extracts the button number from SGR mouse data like "64;10;20".
func parseSGRButton(data []byte) int {
	n := 0
	for _, b := range data {
		if b == ';' {
			break
		}
		if b >= '0' && b <= '9' {
			n = n*10 + int(b-'0')
		}
	}
	return n
}

func decodeRune(data []byte) (rune, int) {
	if len(data) == 0 {
		return 0, 0
	}
	b := data[0]
	if b < 0x80 {
		return rune(b), 1
	}
	var r rune
	var size int
	switch {
	case b&0xE0 == 0xC0:
		size = 2
		r = rune(b & 0x1F)
	case b&0xF0 == 0xE0:
		size = 3
		r = rune(b & 0x0F)
	case b&0xF8 == 0xF0:
		size = 4
		r = rune(b & 0x07)
	default:
		return '?', 1
	}
	if len(data) < size {
		return '?', 1
	}
	for i := 1; i < size; i++ {
		r = r<<6 | rune(data[i]&0x3F)
	}
	return r, size
}

// hasPrefixAt checks if data[offset:] starts with prefix.
func hasPrefixAt(data []byte, offset int, prefix []byte) bool {
	if offset+len(prefix) > len(data) {
		return false
	}
	for i, b := range prefix {
		if data[offset+i] != b {
			return false
		}
	}
	return true
}

// indexBytes finds the first occurrence of needle in haystack, returning -1 if not found.
func indexBytes(haystack, needle []byte) int {
	for i := 0; i <= len(haystack)-len(needle); i++ {
		found := true
		for j, b := range needle {
			if haystack[i+j] != b {
				found = false
				break
			}
		}
		if found {
			return i
		}
	}
	return -1
}
