package api

import (
	"github.com/alexpatri/nexus-systems-api/internal/handler"

	"github.com/gofiber/fiber/v3"
	"github.com/gofiber/fiber/v3/middleware/cors"
)

func NewApp(h *handler.Handler) *fiber.App {
	app := fiber.New()
	app.Use(cors.New(cors.Config{
		ExposeHeaders: fiber.HeaderETag,
		AllowHeaders:  fiber.HeaderIfNoneMatch,
		// O If-None-Match faz toda revalidação de catálogo pedir preflight a
		// outra origem; 2 h é o máximo que o Chrome guarda.
		MaxAge: 7200,
	}))

	app.Get("/health", h.Health)
	app.Get("/api", h.Index)

	// O Fiber casa rotas na ordem de registro e o primeiro match vence, então
	// estas duas capturam qualquer /api/x/y[/z] declarado abaixo delas.
	// Rota nova que não seja catálogo vai na raiz, não sob /api.
	app.Get("/api/:system/:version", h.Manifest)
	app.Get("/api/:system/:version/:catalog", h.Catalog)

	return app
}
