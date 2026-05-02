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
	app.Get("/characters", dndService.GetCharactersHandler)

	characterGroup := app.Group("/character")
	characterGroup.Get("/:id", dndService.GetCharacterHandler)
	characterGroup.Post("/", dndService.PostCharacterHandler)
	characterGroup.Put("/:id", dndService.PutCharacterHandler)
	characterGroup.Delete("/:id", dndService.DeleteCharacterHandler)

	app.Get("/campaigns", dndService.GetCampaignsHandler)

	campaignGroup := app.Group("/campaign")
	campaignGroup.Post("/", dndService.CreateCampaignHandler)
	campaignGroup.Post("/:id", dndService.GetCampaignHandler)
	campaignGroup.Put("/:id", dndService.PutCampaignHandler)
	campaignGroup.Delete("/:id", dndService.DeleteCampaignHandler)

	userService, err := services.NewUserService(cfg.DB)
	if err != nil {
		return nil, err
	}

	userGroup := app.Group("/user")
	userGroup.Post("/", userService.CreateUserHandler)
	userGroup.Post("/login", userService.ValidateUserHandler)

	return app, nil
}
