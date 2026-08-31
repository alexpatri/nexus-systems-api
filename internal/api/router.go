package api

import (
	"rpg-nexus/api/systems/data"
	"rpg-nexus/api/systems/internal/registry"

	"github.com/gofiber/fiber/v3"
	"github.com/gofiber/fiber/v3/middleware/cors"
)

func NewApp() (*fiber.App, error) {
	reg, err := registry.Load(data.Systems())
	if err != nil {
		return nil, err
	}

	app := fiber.New()
	app.Use(cors.New(cors.Config{
		ExposeHeaders: fiber.HeaderETag,
		AllowHeaders:  fiber.HeaderIfNoneMatch,
	}))

	handlers := registry.NewHandlers(reg)

	app.Get("/health", func(c fiber.Ctx) error {
		return c.JSON(fiber.Map{"systems": len(reg.All())})
	})

	app.Get("/api", handlers.Index)

	// O Fiber casa rotas na ordem de registro e o primeiro match vence, então
	// estas duas capturam qualquer /api/x/y[/z] declarado abaixo delas.
	// Rota nova que não seja catálogo vai na raiz, não sob /api.
	app.Get("/api/:system/:version", handlers.Manifest)
	app.Get("/api/:system/:version/:catalog", handlers.Catalog)

	return app, nil
}
