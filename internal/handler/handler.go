// Package handler expõe o registry de sistemas por HTTP. Ele conhece o
// registry; o inverso não vale.
package handler

import (
	"rpg-nexus/api/systems/internal/registry"

	"github.com/gofiber/fiber/v3"
)

const cacheControl = "public, max-age=300, must-revalidate"

type Handler struct {
	reg *registry.Registry
}

func New(reg *registry.Registry) *Handler {
	return &Handler{reg: reg}
}

type systemInfo struct {
	ID       string   `json:"id"`
	Version  string   `json:"version"`
	Name     string   `json:"name"`
	Source   string   `json:"source"`
	Href     string   `json:"href"`
	Catalogs []string `json:"catalogs"`
}

func (h *Handler) Health(c fiber.Ctx) error {
	return c.JSON(fiber.Map{"systems": len(h.reg.All())})
}

func (h *Handler) Index(c fiber.Ctx) error {
	all := h.reg.All()
	systems := make([]systemInfo, 0, len(all))
	for _, s := range all {
		systems = append(systems, systemInfo{
			ID:       s.ID,
			Version:  s.Version,
			Name:     s.Name,
			Source:   s.CatalogSource,
			Href:     "/api/" + s.ID + "/" + s.Version,
			Catalogs: s.CatalogKeys(),
		})
	}
	return c.JSON(fiber.Map{"systems": systems})
}

func (h *Handler) Manifest(c fiber.Ctx) error {
	sys, ok := h.reg.System(c.Params("system"), c.Params("version"))
	if !ok {
		return fiber.ErrNotFound
	}
	return send(c, sys.Manifest, sys.ManifestETag)
}

func (h *Handler) Catalog(c fiber.Ctx) error {
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
