package api

import (
	"rpg-nexus/api/dnd/internal/repository"
	"rpg-nexus/api/dnd/internal/services"

	"github.com/gofiber/fiber/v3"
	"github.com/gofiber/fiber/v3/middleware/cors"
	"go.mongodb.org/mongo-driver/mongo"
)

func NewApp(db *mongo.Database) (*fiber.App, error) {
	app := fiber.New()
	app.Use(cors.New())

	catalogRepo := repository.NewCatalog(db)

	dndService, err := services.NewDndService(catalogRepo)
	if err != nil {
		return nil, err
	}

	app.Get("/classes", dndService.GetClassesHandler)
	app.Get("/races", dndService.GetRacesHandler)
	app.Get("/backgrounds", dndService.GetBackgroundsHandler)
	app.Get("/skills", dndService.GetSkillsHandler)

	return app, nil
}
