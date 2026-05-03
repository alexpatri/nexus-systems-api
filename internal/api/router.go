package api

import (
	"rpg-nexus/api/dnd/internal/config"
	"rpg-nexus/api/dnd/internal/services"

	"github.com/gofiber/fiber/v3"
	"github.com/gofiber/fiber/v3/middleware/cors"
)

func NewApp(cfg *config.Config) (*fiber.App, error) {
	app := fiber.New()
	app.Use(cors.New())

	dndService, err := services.NewDndService(cfg.DB)
	if err != nil {
		return nil, err
	}

	app.Get("/classes", dndService.GetClassesHandler)
	app.Get("/races", dndService.GetRacesHandler)
	app.Get("/backgrounds", dndService.GetBackgroundsHandler)
	app.Get("/skills", dndService.GetSkillsHandler)

	return app, nil
}
