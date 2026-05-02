package main

import (
    "alexsandro/ps-back-end-alexsandro-junior/userservice"
    "alexsandro/ps-back-end-alexsandro-junior/dndservice"
    "github.com/gofiber/fiber/v3"
    "github.com/gofiber/fiber/v3/middleware/cors"
)

func NewApp() *fiber.App {
    app := fiber.New()
    app.Use(cors.New())

    dndService, err := dndservice.NewDndService()
    if err != nil {
        return nil
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

    userService, err := userservice.NewUserService()
    if err != nil {
        return nil
    }

    userGroup := app.Group("/user")
    userGroup.Post("/", userService.CreateUserHandler)
    userGroup.Post("/login", userService.ValidateUserHandler)

    return app
}
