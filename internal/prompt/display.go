package prompt

import (
	"regexp"
	"strings"
)

var varRegex = regexp.MustCompile(`\[([A-Z][A-Z0-9_]*)\]`)

// ParseVariables extracts [VARIABLE] placeholder names from template text.
func ParseVariables(templateText string) []string {
	matches := varRegex.FindAllStringSubmatch(templateText, -1)
	seen := make(map[string]bool)
	var result []string
	for _, m := range matches {
		v := m[1]
		if !seen[v] {
			seen[v] = true
			result = append(result, v)
		}
	}
	return result
}

// FillVariables replaces [VARIABLE] placeholders with user-provided values.
func FillVariables(templateText string, values map[string]string) string {
	for k, v := range values {
		templateText = strings.ReplaceAll(templateText, "["+k+"]", v)
	}
	return templateText
}

// FormatPrompt assembles the final prompt by appending the addon suffix.
func FormatPrompt(baseText string, addonSuffix string) string {
	return baseText + addonSuffix
}
