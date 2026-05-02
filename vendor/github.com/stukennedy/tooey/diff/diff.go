package diff

import "github.com/stukennedy/tooey/cell"

// Change represents a horizontal run of changed cells at a position.
type Change struct {
	X, Y  int
	Cells []cell.Cell
}

// Diff compares two buffers and returns the minimal set of changes.
// Both buffers must have the same dimensions.
func Diff(prev, next *cell.Buffer) []Change {
	if prev.Width != next.Width || prev.Height != next.Height {
		// Full redraw if sizes differ
		return fullRedraw(next)
	}

	var changes []Change
	w := next.Width

	for y := 0; y < next.Height; y++ {
		var run []cell.Cell
		runStart := 0

		for x := 0; x < w; x++ {
			pi := y*w + x
			pc := prev.Cells[pi]
			nc := next.Cells[pi]

			if pc != nc {
				if run == nil {
					runStart = x
				}
				run = append(run, nc)
			} else if run != nil {
				changes = append(changes, Change{X: runStart, Y: y, Cells: run})
				run = nil
			}
		}
		if run != nil {
			changes = append(changes, Change{X: runStart, Y: y, Cells: run})
		}
	}

	return changes
}

func fullRedraw(buf *cell.Buffer) []Change {
	changes := make([]Change, buf.Height)
	for y := 0; y < buf.Height; y++ {
		start := y * buf.Width
		end := start + buf.Width
		row := make([]cell.Cell, buf.Width)
		copy(row, buf.Cells[start:end])
		changes[y] = Change{X: 0, Y: y, Cells: row}
	}
	return changes
}
