package prompt

import (
	"testing"
)

func TestParseVariables(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected []string
	}{
		{"no variables", "hello world", nil},
		{"single variable", "hello [NAME]", []string{"NAME"}},
		{"multiple variables", "[ROLE] doing [TASK] with [TOOL]", []string{"ROLE", "TASK", "TOOL"}},
		{"duplicate variables", "[ROLE] and [ROLE] again", []string{"ROLE"}},
		{"lowercase ignored", "hello [name] world", nil},
		{"mixed case", "[Name] vs [NAME]", []string{"NAME"}},
		{"with numbers", "[VAR_1] and [VAR_2]", []string{"VAR_1", "VAR_2"}},
		{"empty string", "", nil},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ParseVariables(tt.input)
			if len(result) != len(tt.expected) {
				t.Fatalf("expected %v, got %v", tt.expected, result)
			}
			for i, v := range result {
				if v != tt.expected[i] {
					t.Errorf("index %d: expected %q, got %q", i, tt.expected[i], v)
				}
			}
		})
	}
}

func TestFillVariables(t *testing.T) {
	tests := []struct {
		name     string
		template string
		values   map[string]string
		expected string
	}{
		{"single", "hello [NAME]", map[string]string{"NAME": "Alice"}, "hello Alice"},
		{"multiple", "[ROLE] doing [TASK]", map[string]string{"ROLE": "Dev", "TASK": "coding"}, "Dev doing coding"},
		{"missing value", "hello [NAME]", map[string]string{}, "hello [NAME]"},
		{"no placeholders", "plain text", map[string]string{"X": "Y"}, "plain text"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := FillVariables(tt.template, tt.values)
			if result != tt.expected {
				t.Errorf("expected %q, got %q", tt.expected, result)
			}
		})
	}
}

func TestFormatPrompt(t *testing.T) {
	result := FormatPrompt("base text", " suffix")
	expected := "base text suffix"
	if result != expected {
		t.Errorf("expected %q, got %q", expected, result)
	}
}
