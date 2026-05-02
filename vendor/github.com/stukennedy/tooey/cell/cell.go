package cell

import "github.com/stukennedy/tooey/node"

// Cell represents a single terminal cell.
type Cell struct {
	Rune  rune
	FG    node.Color
	BG    node.Color
	Style node.StyleFlags
}

// Buffer is a row-major flat cell buffer representing a terminal frame.
type Buffer struct {
	Width  int
	Height int
	Cells  []Cell
}

// NewBuffer creates a buffer filled with spaces.
func NewBuffer(w, h int) *Buffer {
	cells := make([]Cell, w*h)
	for i := range cells {
		cells[i].Rune = ' '
	}
	return &Buffer{Width: w, Height: h, Cells: cells}
}

// inBounds checks if coordinates are valid.
func (b *Buffer) inBounds(x, y int) bool {
	return x >= 0 && x < b.Width && y >= 0 && y < b.Height
}

// Set writes a cell at (x, y).
func (b *Buffer) Set(x, y int, c Cell) {
	if !b.inBounds(x, y) {
		return
	}
	b.Cells[y*b.Width+x] = c
}

// Get reads a cell at (x, y). Returns empty cell if out of bounds.
func (b *Buffer) Get(x, y int) Cell {
	if !b.inBounds(x, y) {
		return Cell{}
	}
	return b.Cells[y*b.Width+x]
}

// Clear resets all cells to spaces with default colors.
func (b *Buffer) Clear() {
	for i := range b.Cells {
		b.Cells[i] = Cell{Rune: ' '}
	}
}

// WriteString writes a string horizontally starting at (x, y).
func (b *Buffer) WriteString(x, y int, s string, fg, bg node.Color, style node.StyleFlags) {
	col := x
	for _, r := range s {
		if !b.inBounds(col, y) {
			break
		}
		b.Cells[y*b.Width+col] = Cell{Rune: r, FG: fg, BG: bg, Style: style}
		col++
	}
}
