package tui

import "testing"

func TestApplyAddonByOrder(t *testing.T) {
	base := "line1\nline2\nline3\nline4"
	addon := "ADDON"

	first := applyAddonByOrder(base, addon, "first")
	if first != addon+"\n\n"+base {
		t.Fatalf("unexpected first placement: %q", first)
	}

	end := applyAddonByOrder(base, addon, "end")
	if end != base+"\n\n"+addon {
		t.Fatalf("unexpected end placement: %q", end)
	}

	mid := applyAddonByOrder(base, addon, "middle")
	if mid == base || mid == first || mid == end {
		t.Fatalf("middle placement should produce distinct output, got: %q", mid)
	}
}

func TestSelectAddonRecommendation(t *testing.T) {
	seg := AddonRecommendSegment{
		Items: []AddonRecommendItem{
			{Index: 1, Mode: "quality", Name: "Q", Description: "d", Suffix: "s", Score: 1},
			{Index: 2, Mode: "speed", Name: "S", Description: "d2", Suffix: "s2", Score: 0.5},
		},
	}
	got, ok := selectAddonRecommendation(seg, 2)
	if !ok {
		t.Fatal("expected selection 2")
	}
	if got.Mode != "speed" || got.Name != "S" {
		t.Fatalf("unexpected item: %+v", got)
	}
	if _, ok := selectAddonRecommendation(seg, 9); ok {
		t.Fatal("expected miss for index 9")
	}
}

func TestParseAddonOrder(t *testing.T) {
	tests := map[string]string{
		"1":      "first",
		"first":  "first",
		"top":    "first",
		"2":      "middle",
		"middle": "middle",
		"3":      "end",
		"end":    "end",
		"last":   "end",
	}
	for in, want := range tests {
		got, ok := parseAddonOrder(in)
		if !ok {
			t.Fatalf("expected %q to parse", in)
		}
		if got != want {
			t.Fatalf("for %q expected %q got %q", in, want, got)
		}
	}

	if _, ok := parseAddonOrder("nope"); ok {
		t.Fatal("expected invalid order to fail parsing")
	}
}
