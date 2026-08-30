package api

import (
	"log"

	"rpg-nexus/api/systems/data"
	"rpg-nexus/api/systems/internal/registry"
	"rpg-nexus/api/systems/internal/repository"
	"rpg-nexus/api/systems/internal/services"

	"github.com/gofiber/fiber/v3"
	"github.com/gofiber/fiber/v3/middleware/cors"
	"go.mongodb.org/mongo-driver/mongo"
)

func NewApp(db *mongo.Database) (*fiber.App, error) {
	reg, err := registry.Load(data.Systems())
	if err != nil {
		return nil, err
	}

	dnd, mongoUp := dndHandlers(db)

	app := fiber.New()
	app.Use(cors.New(cors.Config{
		ExposeHeaders: fiber.HeaderETag,
		AllowHeaders:  fiber.HeaderIfNoneMatch,
	}))

	app.Get("/health", func(c fiber.Ctx) error {
		return c.JSON(fiber.Map{"mongo": mongoUp})
	})

	handlers := registry.NewHandlers(reg, func(s *registry.System) bool {
		return s.CatalogSource != registry.SourceMongo || mongoUp
	})

	app.Get("/api", handlers.Index)

	app.Get("/api/dnd/5e/classes", dnd.GetClassesHandler)
	app.Get("/api/dnd/5e/races", dnd.GetRacesHandler)
	app.Get("/api/dnd/5e/backgrounds", dnd.GetBackgroundsHandler)
	app.Get("/api/dnd/5e/skills", dnd.GetSkillsHandler)

	// O Fiber casa rotas na ordem de registro e o primeiro match vence, então
	// estas duas capturam qualquer /api/x/y[/z] declarado abaixo delas.
	// Rota nova que não seja catálogo vai na raiz, não sob /api.
	app.Get("/api/:system/:version", handlers.Manifest)
	app.Get("/api/:system/:version/:catalog", handlers.Catalog)

	return app, nil
}

func dndHandlers(db *mongo.Database) (services.DndHandlers, bool) {
	if db == nil {
		return services.Unavailable("banco indisponível no boot"), false
	}

	svc, err := services.NewDndService(repository.NewCatalog(db))
	if err != nil {
		log.Printf("aviso: catálogos dnd/5e não carregados: %v", err)
		return services.Unavailable(err.Error()), false
	}

	return svc, true
}
