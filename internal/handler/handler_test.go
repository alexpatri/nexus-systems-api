package handler_test

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"testing/fstest"

	"rpg-nexus/api/systems/internal/api"
	"rpg-nexus/api/systems/internal/handler"
	"rpg-nexus/api/systems/internal/registry"

	"github.com/gofiber/fiber/v3"
)

const originsBody = `{"origins":[{"id":"noble"},{"id":"outlander"}]}`

func newApp(t *testing.T) *fiber.App {
	t.Helper()

	fsys := fstest.MapFS{}
	for name, content := range map[string]string{
		"vileborn/v1/system.json":  `{"id":"vileborn","apiVersion":"v1","name":"Vileborn","catalogs":["origins.json"]}`,
		"vileborn/v1/origins.json": originsBody,
		"dnd/5e/system.json":       `{"id":"dnd","apiVersion":"5e","name":"D&D 5e","catalogs":[]}`,
	} {
		fsys[name] = &fstest.MapFile{Data: []byte(content)}
	}

	reg, err := registry.Load(fsys)
	if err != nil {
		t.Fatalf("registry.Load: %v", err)
	}
	return api.NewApp(handler.New(reg))
}

func get(t *testing.T, app *fiber.App, path string, header ...string) *http.Response {
	t.Helper()

	req := httptest.NewRequest(http.MethodGet, path, nil)
	for i := 0; i+1 < len(header); i += 2 {
		req.Header.Set(header[i], header[i+1])
	}
	res, err := app.Test(req)
	if err != nil {
		t.Fatalf("GET %s: %v", path, err)
	}
	return res
}

func body(t *testing.T, res *http.Response) string {
	t.Helper()

	raw, err := io.ReadAll(res.Body)
	if err != nil {
		t.Fatalf("ler corpo: %v", err)
	}
	return string(raw)
}

func etagOf(t *testing.T, app *fiber.App, path string) string {
	t.Helper()

	tag := get(t, app, path).Header.Get(fiber.HeaderETag)
	if tag == "" {
		t.Fatalf("%s não devolveu ETag", path)
	}
	return tag
}

func TestHealthCountsSystems(t *testing.T) {
	res := get(t, newApp(t), "/health")
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, quer 200", res.StatusCode)
	}

	var payload struct{ Systems int }
	if err := json.Unmarshal([]byte(body(t, res)), &payload); err != nil {
		t.Fatalf("corpo não é JSON: %v", err)
	}
	if payload.Systems != 2 {
		t.Errorf("systems = %d, quer 2", payload.Systems)
	}
}

func TestIndexIsOrderedAndStripsJSONSuffix(t *testing.T) {
	res := get(t, newApp(t), "/api")

	var payload struct {
		Systems []struct {
			ID, Version, Name, Source, Href string
			Catalogs                        []string
		}
	}
	if err := json.Unmarshal([]byte(body(t, res)), &payload); err != nil {
		t.Fatalf("corpo não é JSON: %v", err)
	}

	var got []string
	for _, s := range payload.Systems {
		got = append(got, s.ID+"/"+s.Version)
	}
	// Iteração de map em Go é aleatória; o índice precisa ser byte-estável.
	if strings.Join(got, ",") != "dnd/5e,vileborn/v1" {
		t.Errorf("ordem = %v, quer [dnd/5e vileborn/v1]", got)
	}

	last := payload.Systems[len(payload.Systems)-1]
	if last.Href != "/api/vileborn/v1" {
		t.Errorf("href = %q", last.Href)
	}
	if strings.Join(last.Catalogs, ",") != "origins" {
		t.Errorf("catalogs = %v, quer [origins] sem o sufixo .json", last.Catalogs)
	}
	if last.Source != registry.SourceEmbed {
		t.Errorf("source = %q, quer %q", last.Source, registry.SourceEmbed)
	}
}

func TestManifestServesRawBytes(t *testing.T) {
	app := newApp(t)
	res := get(t, app, "/api/vileborn/v1")

	if res.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, quer 200", res.StatusCode)
	}
	if ct := res.Header.Get(fiber.HeaderContentType); !strings.HasPrefix(ct, fiber.MIMEApplicationJSON) {
		t.Errorf("content-type = %q", ct)
	}
	if !strings.Contains(body(t, res), `"apiVersion"`) {
		t.Error("manifesto não parece o system.json")
	}
}

func TestCatalogAcceptsOptionalJSONSuffix(t *testing.T) {
	app := newApp(t)

	bare := get(t, app, "/api/vileborn/v1/origins")
	suffixed := get(t, app, "/api/vileborn/v1/origins.json")

	if got := body(t, bare); got != originsBody {
		t.Errorf("corpo = %q, quer os bytes crus do arquivo", got)
	}
	if body(t, suffixed) != originsBody {
		t.Error("com o sufixo .json o corpo diverge")
	}
	if bare.Header.Get(fiber.HeaderETag) != suffixed.Header.Get(fiber.HeaderETag) {
		t.Error("com e sem sufixo devem compartilhar o ETag")
	}
}

func TestLookupIsCaseInsensitive(t *testing.T) {
	// O Fiber casa a rota ignorando caixa, mas Params preserva o original.
	res := get(t, newApp(t), "/api/VileBorn/V1/Origins")
	if res.StatusCode != http.StatusOK {
		t.Errorf("status = %d, quer 200", res.StatusCode)
	}
}

func TestNotFound(t *testing.T) {
	app := newApp(t)
	for name, path := range map[string]string{
		"sistema inexistente":  "/api/pathfinder/v1",
		"versão inexistente":   "/api/vileborn/v2",
		"catálogo inexistente": "/api/vileborn/v1/spells",
	} {
		t.Run(name, func(t *testing.T) {
			if res := get(t, app, path); res.StatusCode != http.StatusNotFound {
				t.Errorf("status = %d, quer 404", res.StatusCode)
			}
		})
	}
}

func TestCacheHeaders(t *testing.T) {
	res := get(t, newApp(t), "/api/vileborn/v1/origins")

	tag := res.Header.Get(fiber.HeaderETag)
	// A RFC 9110 exige as aspas, e o matchEtag do Fiber compara a string inteira.
	if !strings.HasPrefix(tag, `"`) || !strings.HasSuffix(tag, `"`) {
		t.Errorf("ETag = %s, quer entre aspas", tag)
	}
	// Sem Cache-Control o navegador nunca manda o condicional.
	if res.Header.Get(fiber.HeaderCacheControl) == "" {
		t.Error("resposta sem Cache-Control")
	}
}

func TestConditionalRequestReturns304(t *testing.T) {
	app := newApp(t)
	const path = "/api/vileborn/v1/origins"
	tag := etagOf(t, app, path)

	for name, value := range map[string]string{
		"forte": tag,
		"fraco": "W/" + tag,
		"lista": `"outro", ` + tag,
	} {
		t.Run(name, func(t *testing.T) {
			res := get(t, app, path, fiber.HeaderIfNoneMatch, value)
			if res.StatusCode != http.StatusNotModified {
				t.Errorf("status = %d, quer 304", res.StatusCode)
			}
		})
	}

	t.Run("etag divergente", func(t *testing.T) {
		res := get(t, app, path, fiber.HeaderIfNoneMatch, `"nao-bate"`)
		if res.StatusCode != http.StatusOK {
			t.Errorf("status = %d, quer 200", res.StatusCode)
		}
	})
}

func TestIfModifiedSinceAloneDoesNotReturn304(t *testing.T) {
	// Fresh() no beta.2 devolve true quando vem If-Modified-Since sem
	// If-None-Match, o que daria 304 a quem não tem nada em cache. O handler
	// guarda contra isso; sem a guarda este teste falha.
	res := get(t, newApp(t), "/api/vileborn/v1/origins",
		fiber.HeaderIfModifiedSince, "Thu, 01 Jan 1970 00:00:00 GMT")

	if res.StatusCode != http.StatusOK {
		t.Errorf("status = %d, quer 200", res.StatusCode)
	}
}

func TestCORSExposesETag(t *testing.T) {
	// ETag não é safelisted: sem ExposeHeaders o JS do navegador não o lê.
	res := get(t, newApp(t), "/api/vileborn/v1/origins",
		fiber.HeaderOrigin, "http://localhost:5173")

	if got := res.Header.Get(fiber.HeaderAccessControlExposeHeaders); !strings.Contains(got, fiber.HeaderETag) {
		t.Errorf("Access-Control-Expose-Headers = %q, quer conter ETag", got)
	}
}
