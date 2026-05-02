package layout

import (
	"strings"
	"unicode/utf8"

	"github.com/stukennedy/tooey/node"
)

// Rect is a positioned rectangle in terminal coordinates.
type Rect struct {
	X, Y, W, H int
}

// LayoutNode is a positioned node with resolved layout.
type LayoutNode struct {
	Node     node.Node
	Rect     Rect
	Children []LayoutNode
}

// Layout computes positions for the node tree within the given terminal size.
func Layout(root node.Node, termW, termH int) LayoutNode {
	return layout(root, Rect{0, 0, termW, termH})
}

func layout(n node.Node, avail Rect) LayoutNode {
	ln := LayoutNode{Node: n, Rect: avail}

	switch n.Type {
	case node.TextNode:
		ln = layoutText(n, avail)
	case node.RowNode:
		ln = layoutRow(n, avail)
	case node.ColumnNode, node.ListNode, node.PaneNode:
		ln = layoutColumn(n, avail)
	case node.BoxNode:
		ln = layoutBox(n, avail)
	case node.SpacerNode:
		ln.Rect = avail
	}

	// Apply explicit size constraints
	if n.Props.Width > 0 && n.Props.Width < ln.Rect.W {
		ln.Rect.W = n.Props.Width
	}
	if n.Props.Height > 0 && n.Props.Height < ln.Rect.H {
		ln.Rect.H = n.Props.Height
	}

	return ln
}

func layoutText(n node.Node, avail Rect) LayoutNode {
	lines := wrapText(n.Props.Text, avail.W)
	h := len(lines)
	if h > avail.H {
		h = avail.H
	}
	// Text uses the full available width (important for flex-allocated space)
	return LayoutNode{
		Node: n,
		Rect: Rect{avail.X, avail.Y, avail.W, h},
	}
}

func layoutRow(n node.Node, avail Rect) LayoutNode {
	ln := LayoutNode{Node: n, Rect: avail}
	if len(n.Children) == 0 {
		return ln
	}

	// First pass: measure non-flex children
	totalFixed := 0
	totalFlex := 0
	for _, child := range n.Children {
		fw := flexWeight(child)
		if fw > 0 {
			totalFlex += fw
		} else {
			totalFixed += measureWidth(child, avail)
		}
	}

	remaining := avail.W - totalFixed
	if remaining < 0 {
		remaining = 0
	}

	// Second pass: assign positions
	x := avail.X
	for _, child := range n.Children {
		fw := flexWeight(child)
		var childW int
		if fw > 0 && totalFlex > 0 {
			childW = (remaining * fw) / totalFlex
		} else {
			childW = measureWidth(child, avail)
		}
		if childW > avail.W-(x-avail.X) {
			childW = avail.W - (x - avail.X)
		}
		if childW < 0 {
			childW = 0
		}
		childRect := Rect{x, avail.Y, childW, avail.H}
		ln.Children = append(ln.Children, layout(child, childRect))
		x += childW
	}

	return ln
}

func layoutColumn(n node.Node, avail Rect) LayoutNode {
	ln := LayoutNode{Node: n, Rect: avail}
	if len(n.Children) == 0 {
		return ln
	}

	scrollable := n.Props.ScrollOffset > 0 || n.Props.ScrollToBottom

	// First pass: measure non-flex children
	totalFixed := 0
	totalFlex := 0
	for _, child := range n.Children {
		fw := flexWeight(child)
		if fw > 0 {
			totalFlex += fw
		} else {
			totalFixed += measureHeight(child, avail)
		}
	}

	remaining := avail.H - totalFixed
	if remaining < 0 {
		remaining = 0
	}

	// Second pass: assign positions
	y := avail.Y
	for _, child := range n.Children {
		fw := flexWeight(child)
		var childH int
		if fw > 0 && totalFlex > 0 {
			childH = (remaining * fw) / totalFlex
		} else {
			childH = measureHeight(child, avail)
		}
		if !scrollable {
			if childH > avail.H-(y-avail.Y) {
				childH = avail.H - (y - avail.Y)
			}
			if childH < 0 {
				childH = 0
			}
		}
		childRect := Rect{avail.X, y, avail.W, childH}
		ln.Children = append(ln.Children, layout(child, childRect))
		y += childH
	}

	// Apply scroll offset: shift children upward
	scrollOffset := n.Props.ScrollOffset
	if n.Props.ScrollToBottom {
		totalContentH := y - avail.Y
		if totalContentH > avail.H {
			autoOffset := totalContentH - avail.H
			// Manual scroll (scrollOffset) adjusts from the auto-scroll position
			scrollOffset = autoOffset - n.Props.ScrollOffset
			if scrollOffset < 0 {
				scrollOffset = 0
			}
		} else {
			scrollOffset = 0
		}
	}
	if scrollOffset > 0 {
		for i := range ln.Children {
			shiftY(&ln.Children[i], -scrollOffset)
		}
	}

	return ln
}

func layoutBox(n node.Node, avail Rect) LayoutNode {
	ln := LayoutNode{Node: n, Rect: avail}
	if len(n.Children) == 0 {
		return ln
	}
	// Border takes 1 cell on each side
	innerRect := Rect{
		X: avail.X + 1,
		Y: avail.Y + 1,
		W: avail.W - 2,
		H: avail.H - 2,
	}
	if innerRect.W < 0 {
		innerRect.W = 0
	}
	if innerRect.H < 0 {
		innerRect.H = 0
	}
	ln.Children = append(ln.Children, layout(n.Children[0], innerRect))
	return ln
}

// measureWidth returns the intrinsic width of a non-flex node.
func measureWidth(n node.Node, avail Rect) int {
	if n.Props.Width > 0 {
		return n.Props.Width
	}
	switch n.Type {
	case node.TextNode:
		return utf8.RuneCountInString(n.Props.Text)
	case node.BoxNode:
		if len(n.Children) > 0 {
			return measureWidth(n.Children[0], avail) + 2
		}
		return 2
	case node.RowNode:
		w := 0
		for _, c := range n.Children {
			w += measureWidth(c, avail)
		}
		return w
	default:
		return avail.W
	}
}

// measureHeight returns the intrinsic height of a non-flex node.
func measureHeight(n node.Node, avail Rect) int {
	if n.Props.Height > 0 {
		return n.Props.Height
	}
	switch n.Type {
	case node.TextNode:
		lines := wrapText(n.Props.Text, avail.W)
		return len(lines)
	case node.BoxNode:
		if len(n.Children) > 0 {
			innerAvail := Rect{X: avail.X, Y: avail.Y, W: avail.W - 2, H: avail.H}
			if innerAvail.W < 0 {
				innerAvail.W = 0
			}
			return measureHeight(n.Children[0], innerAvail) + 2
		}
		return 2
	case node.ColumnNode, node.ListNode, node.PaneNode:
		h := 0
		for _, c := range n.Children {
			h += measureHeight(c, avail)
		}
		return h
	case node.RowNode:
		h := 1
		for _, c := range n.Children {
			ch := measureHeight(c, avail)
			if ch > h {
				h = ch
			}
		}
		return h
	default:
		return 1
	}
}

// shiftY recursively shifts a layout node and all descendants by dy.
func shiftY(ln *LayoutNode, dy int) {
	ln.Rect.Y += dy
	for i := range ln.Children {
		shiftY(&ln.Children[i], dy)
	}
}

func flexWeight(n node.Node) int {
	return n.Props.FlexWeight
}

// wrapText wraps text to fit within maxWidth columns.
func wrapText(s string, maxWidth int) []string {
	if maxWidth <= 0 {
		return nil
	}
	if s == "" {
		return []string{""}
	}

	var lines []string
	for _, paragraph := range strings.Split(s, "\n") {
		trimmed := strings.TrimLeft(paragraph, " \t")
		leading := paragraph[:len(paragraph)-len(trimmed)]

		if trimmed == "" {
			lines = append(lines, leading)
			continue
		}
		words := strings.Fields(trimmed)
		if len(words) == 0 {
			lines = append(lines, leading)
			continue
		}
		line := leading + words[0]
		lineLen := utf8.RuneCountInString(line)
		for _, w := range words[1:] {
			wLen := utf8.RuneCountInString(w)
			if lineLen+1+wLen <= maxWidth {
				line += " " + w
				lineLen += 1 + wLen
			} else {
				lines = append(lines, line)
				line = leading + w
				lineLen = utf8.RuneCountInString(leading) + wLen
			}
		}
		lines = append(lines, line)
	}
	return lines
}
