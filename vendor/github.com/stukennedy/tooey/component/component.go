package component

import "github.com/stukennedy/tooey/node"

// Component is the interface for reusable UI components.
type Component interface {
	Render(model interface{}, focused string) node.Node
}

// TextBlock renders a styled text block.
type TextBlock struct {
	Key   string
	FG    node.Color
	BG    node.Color
	Style node.StyleFlags
}

func (t TextBlock) Render(text string) node.Node {
	n := node.TextStyled(text, t.FG, t.BG, t.Style)
	if t.Key != "" {
		n = n.WithKey(t.Key)
	}
	return n
}

// List renders a vertical list of items with selection highlight.
type List struct {
	Key        string
	Items      []string
	Selected   int
	FG         node.Color
	BG         node.Color
	SelectedFG node.Color
	SelectedBG node.Color
}

func (l List) Render(focused string) node.Node {
	children := make([]node.Node, len(l.Items))
	for i, item := range l.Items {
		var n node.Node
		if i == l.Selected {
			n = node.TextStyled("> "+item, l.SelectedFG, l.SelectedBG, node.Bold)
		} else {
			n = node.TextStyled("  "+item, l.FG, l.BG, 0)
		}
		n = n.WithKey(l.Key + "-" + item).WithFocusable()
		children[i] = n
	}
	return node.Column(children...)
}

// Box renders a bordered box with a title.
type Box struct {
	Title  string
	Border node.BorderStyle
}

func (b Box) Render(child node.Node) node.Node {
	// For now, just wrap in a box node. Title rendering is handled at paint level.
	return node.Box(b.Border, child)
}
