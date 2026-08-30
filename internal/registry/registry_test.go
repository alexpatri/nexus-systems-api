package registry

import (
	"encoding/json"
	"strings"
	"testing"
	"testing/fstest"

	"rpg-nexus/api/systems/data"
)

func manifestFor(id, version string, catalogs ...string) string {
	b, _ := json.Marshal(map[string]any{
		"id": id, "apiVersion": version, "name": strings.ToUpper(id), "catalogs": catalogs,
	})
	return string(b)
}

func fsWith(files map[string]string) fstest.MapFS {
	out := fstest.MapFS{}
	for name, body := range files {
		out[name] = &fstest.MapFile{Data: []byte(body)}
	}
	return out
}

func TestLoadDiscoversSystemsAndVersions(t *testing.T) {
	reg, err := Load(fsWith(map[string]string{
		"vileborn/v1/system.json":  manifestFor("vileborn", "v1", "origins.json"),
		"vileborn/v1/origins.json": `{"origins":[]}`,
		"vileborn/v2/system.json":  manifestFor("vileborn", "v2"),
		"dnd/5e/system.json":       manifestFor("dnd", "5e"),
	}))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	for _, want := range [][2]string{{"vileborn", "v1"}, {"vileborn", "v2"}, {"dnd", "5e"}} {
		if _, ok := reg.System(want[0], want[1]); !ok {
			t.Errorf("System(%q, %q) não encontrado", want[0], want[1])
		}
	}
	if _, ok := reg.System("vileborn", "v3"); ok {
		t.Error("System devolveu versão inexistente")
	}
}

func TestSystemLookupIsCaseInsensitive(t *testing.T) {
	reg, err := Load(fsWith(map[string]string{
		"vileborn/v1/system.json": manifestFor("vileborn", "v1"),
	}))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if _, ok := reg.System("VileBorn", "V1"); !ok {
		t.Error("lookup deveria ignorar caixa: o Fiber casa rota case-insensitive")
	}
}

func TestAllIsSorted(t *testing.T) {
	reg, err := Load(fsWith(map[string]string{
		"vileborn/v2/system.json": manifestFor("vileborn", "v2"),
		"vileborn/v1/system.json": manifestFor("vileborn", "v1"),
		"dnd/5e/system.json":      manifestFor("dnd", "5e"),
	}))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	var got []string
	for _, s := range reg.All() {
		got = append(got, s.ID+"/"+s.Version)
	}
	want := []string{"dnd/5e", "vileborn/v1", "vileborn/v2"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("All() = %v, quer %v", got, want)
	}
}

func TestCatalogAcceptsOptionalJSONSuffix(t *testing.T) {
	reg, err := Load(fsWith(map[string]string{
		"vileborn/v1/system.json":  manifestFor("vileborn", "v1", "origins.json"),
		"vileborn/v1/origins.json": `{"origins":[1,2]}`,
	}))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	sys, _ := reg.System("vileborn", "v1")

	bare, bareTag, ok := sys.Catalog("origins")
	if !ok {
		t.Fatal("Catalog(origins) não encontrado")
	}
	suffixed, suffixedTag, ok := sys.Catalog("origins.json")
	if !ok {
		t.Fatal("Catalog(origins.json) não encontrado")
	}
	if string(bare) != string(suffixed) || bareTag != suffixedTag {
		t.Error("com e sem sufixo .json devem devolver o mesmo payload e ETag")
	}
	if _, _, ok := sys.Catalog("spells"); ok {
		t.Error("Catalog devolveu catálogo inexistente")
	}
}

func TestManifestServedAsSystemCatalog(t *testing.T) {
	reg, err := Load(fsWith(map[string]string{
		"vileborn/v1/system.json": manifestFor("vileborn", "v1"),
	}))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	sys, _ := reg.System("vileborn", "v1")

	raw, tag, ok := sys.Catalog("system")
	if !ok {
		t.Fatal(`Catalog("system") não encontrado`)
	}
	if string(raw) != string(sys.Manifest) || tag != sys.ManifestETag {
		t.Error(`Catalog("system") deve espelhar o manifesto`)
	}
}

func TestETagIsStableAndContentAddressed(t *testing.T) {
	build := func(body string) (string, string) {
		reg, err := Load(fsWith(map[string]string{
			"vileborn/v1/system.json":  manifestFor("vileborn", "v1", "origins.json"),
			"vileborn/v1/origins.json": body,
		}))
		if err != nil {
			t.Fatalf("Load: %v", err)
		}
		sys, _ := reg.System("vileborn", "v1")
		_, tag, _ := sys.Catalog("origins")
		return tag, body
	}

	first, _ := build(`{"origins":[]}`)
	again, _ := build(`{"origins":[]}`)
	other, _ := build(`{"origins":[1]}`)

	if first != again {
		t.Error("mesmo conteúdo deve gerar o mesmo ETag entre boots")
	}
	if first == other {
		t.Error("conteúdos distintos devem gerar ETags distintos")
	}
	if !strings.HasPrefix(first, `"`) || !strings.HasSuffix(first, `"`) {
		t.Errorf("ETag precisa vir entre aspas (RFC 9110), veio %s", first)
	}
}

func TestLoadRejectsInconsistentManifest(t *testing.T) {
	cases := map[string]map[string]string{
		"id divergente do diretório": {
			"vileborn/v1/system.json": manifestFor("outro", "v1"),
		},
		"apiVersion divergente do diretório": {
			"vileborn/v1/system.json": manifestFor("vileborn", "v2"),
		},
		"catálogo declarado e ausente": {
			"vileborn/v1/system.json": manifestFor("vileborn", "v1", "origins.json"),
		},
		"catálogo presente e não declarado": {
			"vileborn/v1/system.json": manifestFor("vileborn", "v1"),
			"vileborn/v1/spells.json": `{}`,
		},
		"arquivo solto na raiz": {
			"solto.json": `{}`,
		},
		"sistema sem diretório de versão": {
			"vileborn/system.json": manifestFor("vileborn", "v1"),
		},
	}

	for name, files := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := Load(fsWith(files)); err == nil {
				t.Error("Load deveria falhar no boot")
			}
		})
	}
}

func TestMongoBackedSystemSkipsFileCheck(t *testing.T) {
	body := `{"id":"dnd","apiVersion":"5e","name":"D&D","catalogSource":"mongo","catalogs":["classes.json"]}`
	reg, err := Load(fsWith(map[string]string{"dnd/5e/system.json": body}))
	if err != nil {
		t.Fatalf("catálogos vindos do Mongo não devem exigir arquivo: %v", err)
	}

	sys, _ := reg.System("dnd", "5e")
	if sys.CatalogSource != SourceMongo {
		t.Errorf("CatalogSource = %q, quer %q", sys.CatalogSource, SourceMongo)
	}
	if _, _, ok := sys.Catalog("classes"); ok {
		t.Error("o registry não deve servir catálogo cuja origem é o Mongo")
	}
}

func TestEmbeddedVilebornMatchesManifest(t *testing.T) {
	reg, err := Load(data.Systems())
	if err != nil {
		t.Fatalf("Load da FS embutida: %v", err)
	}

	sys, ok := reg.System("vileborn", "v1")
	if !ok {
		t.Fatal("vileborn/v1 ausente da FS embutida")
	}
	if len(sys.CatalogNames) == 0 {
		t.Fatal("manifesto sem catalogs")
	}
	for _, name := range sys.CatalogNames {
		raw, tag, ok := sys.Catalog(name)
		if !ok {
			t.Errorf("catálogo %s declarado mas não servido", name)
			continue
		}
		if !json.Valid(raw) {
			t.Errorf("catálogo %s não é JSON válido", name)
		}
		if tag == "" {
			t.Errorf("catálogo %s sem ETag", name)
		}
	}
}
