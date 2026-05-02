package focus

import "github.com/stukennedy/tooey/layout"

// Manager tracks focus state across the component tree.
type Manager struct {
	focusables   []string // ordered keys of focusable nodes
	current      int
	contextStack []contextEntry
}

type contextEntry struct {
	focusables []string
	current    int
}

// NewManager creates a new focus manager.
func NewManager() *Manager {
	return &Manager{}
}

// Update rebuilds the focusable list from the layout tree.
// Preserves current focus if the key still exists.
func (m *Manager) Update(tree layout.LayoutNode) {
	oldKey := m.Current()
	m.focusables = nil
	collectFocusables(tree, &m.focusables)

	if oldKey != "" {
		for i, k := range m.focusables {
			if k == oldKey {
				m.current = i
				return
			}
		}
	}
	m.current = 0
}

// Current returns the key of the currently focused node, or "" if none.
func (m *Manager) Current() string {
	if len(m.focusables) == 0 {
		return ""
	}
	if m.current >= len(m.focusables) {
		m.current = 0
	}
	return m.focusables[m.current]
}

// Next moves focus to the next focusable node (Tab).
func (m *Manager) Next() {
	if len(m.focusables) == 0 {
		return
	}
	m.current = (m.current + 1) % len(m.focusables)
}

// Prev moves focus to the previous focusable node (Shift+Tab).
func (m *Manager) Prev() {
	if len(m.focusables) == 0 {
		return
	}
	m.current = (m.current - 1 + len(m.focusables)) % len(m.focusables)
}

// PushContext saves current focus state and enters a new context (pane/modal).
func (m *Manager) PushContext(tree layout.LayoutNode) {
	m.contextStack = append(m.contextStack, contextEntry{
		focusables: m.focusables,
		current:    m.current,
	})
	m.focusables = nil
	collectFocusables(tree, &m.focusables)
	m.current = 0
}

// PopContext restores the previous focus context.
func (m *Manager) PopContext() {
	if len(m.contextStack) == 0 {
		return
	}
	top := m.contextStack[len(m.contextStack)-1]
	m.contextStack = m.contextStack[:len(m.contextStack)-1]
	m.focusables = top.focusables
	m.current = top.current
}

// FocusableCount returns the number of focusable nodes.
func (m *Manager) FocusableCount() int {
	return len(m.focusables)
}

func collectFocusables(ln layout.LayoutNode, keys *[]string) {
	if ln.Node.Props.Focusable && ln.Node.Props.Key != "" {
		*keys = append(*keys, ln.Node.Props.Key)
	}
	for _, child := range ln.Children {
		collectFocusables(child, keys)
	}
}
