package registry

import (
	"strings"

	"github.com/gofiber/fiber/v3"
)

const cacheControl = "public, max-age=300, must-revalidate"

type Handlers struct {
	reg       *Registry
	available func(*System) bool
}

func NewHandlers(reg *Registry, available func(*System) bool) *Handlers {
	return &Handlers{reg: reg, available: available}
}

type systemInfo struct {
	ID        string   `json:"id"`
	Version   string   `json:"version"`
	Name      string   `json:"name"`
	Source    string   `json:"source"`
	Available bool     `json:"available"`
	Href      string   `json:"href"`
	Catalogs  []string `json:"catalogs"`
}

// Index reflete a disponibilidade do Mongo, então é dinâmico e não leva ETag.
func (h *Handlers) Index(c fiber.Ctx) error {
	all := h.reg.All()
	systems := make([]systemInfo, 0, len(all))
	for _, s := range all {
		systems = append(systems, systemInfo{
			ID:        s.ID,
			Version:   s.Version,
			Name:      s.Name,
			Source:    s.CatalogSource,
			Available: h.available(s),
			Href:      "/api/" + s.ID + "/" + s.Version,
			Catalogs:  s.CatalogKeys(),
		})
	}
	return c.JSON(fiber.Map{"systems": systems})
}

func (h *Handlers) Manifest(c fiber.Ctx) error {
	sys, ok := h.reg.System(c.Params("system"), c.Params("version"))
	if !ok {
		return fiber.ErrNotFound
	}
	return send(c, sys.Manifest, sys.ManifestETag)
}

func (h *Handlers) Catalog(c fiber.Ctx) error {
	sys, ok := h.reg.System(c.Params("system"), c.Params("version"))
	if !ok {
		return fiber.ErrNotFound
	}
	raw, etag, ok := sys.Catalog(c.Params("catalog"))
	if !ok {
		return fiber.ErrNotFound
	}
	return send(c, raw, etag)
}

func send(c fiber.Ctx, raw []byte, etag string) error {
	c.Set(fiber.HeaderETag, etag)
	c.Set(fiber.HeaderCacheControl, cacheControl)

	// A guarda do If-None-Match contorna um bug do Fresh() no beta.2: com
	// If-Modified-Since e sem If-None-Match ele devolve true, dando 304 a
	// quem não tem nada em cache.
	if c.Get(fiber.HeaderIfNoneMatch) != "" && c.Fresh() {
		return c.SendStatus(fiber.StatusNotModified)
	}

	c.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	return c.Send(raw)
}

// CatalogKeys devolve os nomes declarados sem o sufixo .json, na ordem do
// manifesto — é a forma que aparece na URL.
func (s *System) CatalogKeys() []string {
	keys := make([]string, 0, len(s.CatalogNames))
	for _, name := range s.CatalogNames {
		keys = append(keys, strings.TrimSuffix(name, ".json"))
	}
	return keys
}
