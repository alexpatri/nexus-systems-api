package fixtures

import (
	"encoding/json"
	"io/fs"
	"testing"
)

func TestEmbedsExpressionCases(t *testing.T) {
	paths, err := fs.Glob(FS(), "shadowrun/5e/expr/*.json")
	if err != nil || len(paths) == 0 {
		t.Fatalf("nenhuma fixture de expressão embutida: %v", err)
	}
	for _, p := range paths {
		raw, _ := fs.ReadFile(FS(), p)
		var doc struct {
			Cases []json.RawMessage `json:"cases"`
		}
		if err := json.Unmarshal(raw, &doc); err != nil || len(doc.Cases) == 0 {
			t.Errorf("%s: %v, %d casos", p, err, len(doc.Cases))
		}
	}
}
