package app

import (
	"context"
	"io"
	"os"
	"time"

	"github.com/stukennedy/tooey/ansi"
	"github.com/stukennedy/tooey/cell"
	"github.com/stukennedy/tooey/diff"
	"github.com/stukennedy/tooey/focus"
	"github.com/stukennedy/tooey/input"
	"github.com/stukennedy/tooey/layout"
	"github.com/stukennedy/tooey/node"
)

// Msg is any message that can trigger a state update.
type Msg interface{}

// KeyMsg wraps a key event as a message.
type KeyMsg struct {
	Key input.Key
}

// ResizeMsg wraps a resize event.
type ResizeMsg struct {
	Width, Height int
}

// FocusMsg indicates the terminal gained or lost focus.
type FocusMsg struct {
	Focused bool
}

// PasteMsg carries text from a bracketed paste event.
type PasteMsg struct {
	Text string
}

// ScrollMsg indicates a mouse scroll event. Delta is positive for scroll up, negative for scroll down.
type ScrollMsg struct {
	Delta int
}

// Cmd is a function that runs asynchronously and returns a Msg.
type Cmd func() Msg

// Sub is a long-running command that can send multiple messages via the send callback.
// It returns a final Msg when done (or nil).
type Sub func(send func(Msg)) Msg

// UpdateResult is returned from Update: new model + optional async commands.
type UpdateResult struct {
	Model interface{}
	Cmds  []Cmd
	Subs  []Sub
}

// NoCmd returns an UpdateResult with no commands.
func NoCmd(model interface{}) UpdateResult {
	return UpdateResult{Model: model}
}

// WithCmd returns an UpdateResult with commands to execute.
func WithCmd(model interface{}, cmds ...Cmd) UpdateResult {
	return UpdateResult{Model: model, Cmds: cmds}
}

// WithSub returns an UpdateResult with subscriptions.
func WithSub(model interface{}, subs ...Sub) UpdateResult {
	return UpdateResult{Model: model, Subs: subs}
}

// App defines an Elm-style TUI application.
type App struct {
	// Init returns the initial model.
	Init func() interface{}

	// Update processes a message and returns the new model + optional commands.
	// Return UpdateResult with nil Model to quit.
	Update func(model interface{}, msg Msg) UpdateResult

	// View renders the model to a node tree.
	View func(model interface{}, focused string) node.Node

	// Output writer (defaults to os.Stdout).
	Output io.Writer

	// Input reader (defaults to os.Stdin).
	Input io.Reader
}

// Run starts the application main loop.
func (a *App) Run(ctx context.Context) error {
	out := a.Output
	if out == nil {
		out = os.Stdout
	}
	in := a.Input
	if in == nil {
		in = os.Stdin
	}

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	// Terminal setup
	ansi.EnterAltScreen(out)
	ansi.HideCursor(out)
	ansi.EnableFocusReporting(out)
	ansi.EnableMouseReporting(out)
	ansi.EnableBracketedPaste(out)
	ansi.ClearScreen(out)
	defer func() {
		ansi.DisableBracketedPaste(out)
		ansi.DisableMouseReporting(out)
		ansi.DisableFocusReporting(out)
		ansi.ShowCursor(out)
		ansi.LeaveAltScreen(out)
	}()

	// Get terminal size
	width, height := input.TermSize()

	model := a.Init()
	fm := focus.NewManager()

	var prevBuf *cell.Buffer

	// Message channels
	keyCh := input.ReadKeys(ctx, in)
	resizeCh := input.WatchResize(ctx)
	cmdCh := make(chan Msg, 64)

	// Frame rate limiter
	frameTicker := time.NewTicker(33 * time.Millisecond) // ~30 FPS
	defer frameTicker.Stop()

	needsRender := true
	msgs := make([]Msg, 0, 16)
 isFirstFrame := true

	for {
 // On first frame, inject initial resize message without blocking
 if isFirstFrame {
     isFirstFrame = false
     msgs = append(msgs, ResizeMsg{Width: width, Height: height})
     needsRender = true
 } else {
		// Collect messages
		select {
		case <-ctx.Done():
			return ctx.Err()
		case k, ok := <-keyCh:
			if !ok {
				return nil
			}
			switch k.Type {
			case input.FocusIn:
				msgs = append(msgs, FocusMsg{Focused: true})
			case input.FocusOut:
				msgs = append(msgs, FocusMsg{Focused: false})
			case input.MouseScrollUp:
				msgs = append(msgs, ScrollMsg{Delta: 3})
			case input.MouseScrollDown:
				msgs = append(msgs, ScrollMsg{Delta: -3})
			case input.Paste:
				msgs = append(msgs, PasteMsg{Text: k.Text})
			default:
				msgs = append(msgs, KeyMsg{Key: k})
			}
			needsRender = true
		case r, ok := <-resizeCh:
			if !ok {
				continue
			}
			width, height = r.Width, r.Height
			ansi.ClearScreen(out) // clear stale content in newly exposed areas
			prevBuf = nil         // force full redraw
			msgs = append(msgs, ResizeMsg{Width: width, Height: height})
			needsRender = true
		case cmdMsg := <-cmdCh:
			msgs = append(msgs, cmdMsg)
			needsRender = true
		case <-frameTicker.C:
			// Process batched messages
		}

  }
		// Drain any additional pending messages
		draining := true
		for draining {
			select {
			case k, ok := <-keyCh:
				if !ok {
					draining = false
					continue
				}
				switch k.Type {
				case input.FocusIn:
					msgs = append(msgs, FocusMsg{Focused: true})
				case input.FocusOut:
					msgs = append(msgs, FocusMsg{Focused: false})
				case input.Paste:
					msgs = append(msgs, PasteMsg{Text: k.Text})
				default:
					msgs = append(msgs, KeyMsg{Key: k})
				}
				needsRender = true
			case cmdMsg := <-cmdCh:
				msgs = append(msgs, cmdMsg)
				needsRender = true
			default:
				draining = false
			}
		}

		if !needsRender {
			continue
		}

		// Handle focus keys before update
		for _, msg := range msgs {
			if km, ok := msg.(KeyMsg); ok {
				switch km.Key.Type {
				case input.Tab:
					fm.Next()
				case input.ShiftTab:
					fm.Prev()
				case input.Escape:
					fm.PopContext()
				}
			}
		}

		// Process all messages through update
		for _, msg := range msgs {
			result := a.Update(model, msg)
			model = result.Model
			if model == nil {
				return nil
			}
			// Launch async commands
			for _, cmd := range result.Cmds {
				c := cmd
				go func() {
					if m := c(); m != nil {
						cmdCh <- m
					}
				}()
			}
			// Launch subscriptions
			for _, sub := range result.Subs {
				s := sub
				go func() {
					if m := s(func(msg Msg) { cmdCh <- msg }); m != nil {
						cmdCh <- m
					}
				}()
			}
		}
		msgs = msgs[:0]

		// Render pipeline
		tree := a.View(model, fm.Current())
		lt := layout.Layout(tree, width, height)
		fm.Update(lt)

		buf := cell.NewBuffer(width, height)
		cell.Paint(buf, lt)

		if prevBuf == nil {
			prevBuf = cell.NewBuffer(width, height) // empty for first frame
		}

		changes := diff.Diff(prevBuf, buf)
		ansi.Render(out, changes)

		prevBuf = buf
		needsRender = false
	}
}
