package component

import "github.com/stukennedy/tooey/node"

// Collapsible renders an expandable/collapsible section.
// When collapsed, only the label with a toggle icon is shown.
func Collapsible(label string, expanded bool, children ...node.Node) node.Node {
	icon := "▶"
	if expanded {
		icon = "▼"
	}
	header := node.Row(
		node.TextStyled(icon+" ", 0, 0, node.Bold),
		node.TextStyled(label, 0, 0, node.Bold),
	)
	if !expanded {
		return header
	}
	all := make([]node.Node, 0, 1+len(children))
	all = append(all, header)
	for _, c := range children {
		all = append(all, node.Indent(2, c))
	}
	return node.Column(all...)
}
