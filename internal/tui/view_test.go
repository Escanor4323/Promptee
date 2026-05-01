package tui

import (
	"strings"
	"testing"

	"github.com/stukennedy/tooey/node"
)

func TestRenderCommandInput(t *testing.T) {
	tests := []struct {
		name      string
		input     string
		wantOK    bool
		wantParts []string // substrings expected somewhere in the node tree text
	}{
		{
			name:   "plain query is not a command",
			input:  "find me a prompt",
			wantOK: false,
		},
		{
			name:      "slash command only",
			input:     "/help",
			wantOK:    true,
			wantParts: []string{"/help"},
		},
		{
			name:      "slash command with args",
			input:     "/ingest ./prompts/",
			wantOK:    true,
			wantParts: []string{"/ingest", "./prompts/"},
		},
		{
			name:      "slash command with multi-word args",
			input:     "/feedback this is good",
			wantOK:    true,
			wantParts: []string{"/feedback", "this is good"},
		},
		{
			name:   "empty string",
			input:  "",
			wantOK: false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			n, ok := renderCommandInput(tc.input)
			if ok != tc.wantOK {
				t.Fatalf("renderCommandInput(%q): ok = %v, want %v", tc.input, ok, tc.wantOK)
			}
			if !ok {
				return
			}
			rendered := collectNodeText(n)
			for _, part := range tc.wantParts {
				if !strings.Contains(rendered, part) {
					t.Errorf("rendered output missing %q\ngot: %q", part, rendered)
				}
			}
		})
	}
}

// collectNodeText recursively gathers all text from a node tree.
func collectNodeText(n node.Node) string {
	var b strings.Builder
	b.WriteString(n.Props.Text)
	for _, child := range n.Children {
		b.WriteString(collectNodeText(child))
	}
	return b.String()
}
