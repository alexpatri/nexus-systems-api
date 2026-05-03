package services

import (
	"rpg-nexus/api/dnd/internal/config"
	"rpg-nexus/api/dnd/internal/database"
	"rpg-nexus/api/dnd/internal/models"

	"github.com/gofiber/fiber/v3"
)

type dndService struct {
	classes     models.Classes
	backgrounds models.Backgrounds
	races       models.Races
	skills      models.Skills
}

func NewDndService(dbCfg config.DatabaseConfig) (*dndService, error) {
	db, err := database.NewMongoDB(dbCfg.URI(), dbCfg.Name)
	if err != nil {
		return nil, err
	}

	var classes models.Classes
	if err := db.Find("classes", struct{}{}, &classes.Docs); err != nil {
		return nil, err
	}

	var races models.Races
	if err := db.Find("races", struct{}{}, &races.Docs); err != nil {
		return nil, err
	}

	var bgs models.Backgrounds
	if err := db.Find("backgrounds", struct{}{}, &bgs.Docs); err != nil {
		return nil, err
	}

	var skills models.Skills
	if err := db.Find("skills", struct{}{}, &skills.Docs); err != nil {
		return nil, err
	}

	return &dndService{
		classes:     classes,
		races:       races,
		backgrounds: bgs,
		skills:      skills,
	}, nil
}

func (dnd *dndService) GetClassesHandler(c fiber.Ctx) error {
	return c.JSON(dnd.classes)
}

func (dnd *dndService) GetRacesHandler(c fiber.Ctx) error {
	return c.JSON(dnd.races)
}

func (dnd *dndService) GetBackgroundsHandler(c fiber.Ctx) error {
	return c.JSON(dnd.backgrounds)
}

func (dnd *dndService) GetSkillsHandler(c fiber.Ctx) error {
	return c.JSON(dnd.skills)
}
