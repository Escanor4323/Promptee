package node

import "strings"

// NodeType identifies the kind of UI node.
type NodeType int

const (
	TextNode NodeType = iota
	BoxNode
	RowNode
	ColumnNode
	ListNode
	PaneNode
	SpacerNode
)

// Color represents an ANSI 256-color value. 0 means default/unset.
type Color uint8

// StyleFlags are bitwise text style attributes.
type StyleFlags uint8

const (
	Bold      StyleFlags = 1 << iota
	Dim
	Italic
	Underline
	Reverse
)

// BorderStyle defines box border appearance.
type BorderStyle int

const (
	BorderNone BorderStyle = iota
	BorderSingle
	BorderDouble
	BorderRounded
)

// Props holds configurable properties for a node.
type Props struct {
	Text       string
	Width      int // 0 = auto
	Height     int // 0 = auto
	FlexWeight int // 0 = no flex, >0 = relative weight
	Border     BorderStyle
	Focusable  bool
	Key        string
	FG           Color
	BG           Color
	Style        StyleFlags
	ScrollOffset   int  // vertical scroll offset for Column/List/Pane
	ScrollToBottom bool // auto-scroll so bottom content is visible
}

// Node represents a virtual UI element in the component tree.
type Node struct {
	Type     NodeType
	Props    Props
	Children []Node
}

// Builder functions

func Text(s string) Node {
	return Node{Type: TextNode, Props: Props{Text: s}}
}

func TextStyled(s string, fg, bg Color, style StyleFlags) Node {
	return Node{Type: TextNode, Props: Props{Text: s, FG: fg, BG: bg, Style: style}}
}

func Row(children ...Node) Node {
	return Node{Type: RowNode, Children: children}
}

func Column(children ...Node) Node {
	return Node{Type: ColumnNode, Children: children}
}

func Box(border BorderStyle, child Node) Node {
	return Node{Type: BoxNode, Props: Props{Border: border}, Children: []Node{child}}
}

func List(children ...Node) Node {
	return Node{Type: ListNode, Children: children}
}

func Pane(children ...Node) Node {
	return Node{Type: PaneNode, Children: children}
}

func Spacer() Node {
	return Node{Type: SpacerNode, Props: Props{FlexWeight: 1}}
}

// WithKey sets the key on a node and returns it.
func (n Node) WithKey(key string) Node {
	n.Props.Key = key
	return n
}

// WithFlex sets the flex weight and returns the node.
func (n Node) WithFlex(weight int) Node {
	n.Props.FlexWeight = weight
	return n
}

// WithSize sets explicit width/height and returns the node.
func (n Node) WithSize(w, h int) Node {
	n.Props.Width = w
	n.Props.Height = h
	return n
}

// WithFocusable marks the node as focusable.
func (n Node) WithFocusable() Node {
	n.Props.Focusable = true
	return n
}

// WithScrollOffset sets the vertical scroll offset.
func (n Node) WithScrollOffset(offset int) Node {
	n.Props.ScrollOffset = offset
	return n
}

func (n Node) WithScrollToBottom() Node {
	n.Props.ScrollToBottom = true
	return n
}

// Bar creates a full-width text node with background color fill.
// Use in a Row; the FlexWeight=1 causes it to stretch to fill available width.
func Bar(text string, fg, bg Color, style StyleFlags) Node {
	return TextStyled(text, fg, bg, style).WithFlex(1)
}

// Separator returns a horizontal line of the given width using "─".
func Separator(width int) Node {
	return TextStyled(strings.Repeat("─", width), 245, 0, 0)
}

// SeparatorStyled returns a horizontal line with a custom character and color.
func SeparatorStyled(ch rune, width int, fg Color) Node {
	return TextStyled(strings.Repeat(string(ch), width), fg, 0, 0)
}

// Truncate truncates text to maxWidth, adding "…" if it exceeds the limit.
func Truncate(text string, maxWidth int) string {
	if maxWidth <= 0 {
		return ""
	}
	runes := []rune(text)
	if len(runes) <= maxWidth {
		return text
	}
	if maxWidth == 1 {
		return "…"
	}
	return string(runes[:maxWidth-1]) + "…"
}

// Indent wraps a child node with left indentation.
func Indent(spaces int, child Node) Node {
	return Row(Text(strings.Repeat(" ", spaces)), child)
}

// Pad wraps a child node with padding on all sides.
func Pad(top, right, bottom, left int, child Node) Node {
	padded := child
	if left > 0 || right > 0 {
		var row []Node
		if left > 0 {
			row = append(row, Text(strings.Repeat(" ", left)))
		}
		row = append(row, padded)
		if right > 0 {
			row = append(row, Text(strings.Repeat(" ", right)))
		}
		padded = Row(row...)
	}
	var col []Node
	for i := 0; i < top; i++ {
		col = append(col, Text(""))
	}
	col = append(col, padded)
	for i := 0; i < bottom; i++ {
		col = append(col, Text(""))
	}
	return Column(col...)
}

// ParagraphOpts configures Paragraph rendering.
type ParagraphOpts struct {
	FG    Color
	BG    Color
	Style StyleFlags
}

// Paragraph splits text on newlines and returns a Column of styled text lines.
func Paragraph(text string, fg, bg Color, style StyleFlags) Node {
	return ParagraphStyled(text, ParagraphOpts{FG: fg, BG: bg, Style: style})
}

// ParagraphStyled splits text on newlines using ParagraphOpts.
func ParagraphStyled(text string, opts ParagraphOpts) Node {
	lines := strings.Split(text, "\n")
	children := make([]Node, len(lines))
	for i, line := range lines {
		children[i] = TextStyled(line, opts.FG, opts.BG, opts.Style)
	}
	return Column(children...)
}
