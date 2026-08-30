package services

import (
	"context"

	"rpg-nexus/api/systems/internal/models"

	"github.com/gofiber/fiber/v3"
)

type CatalogRepository interface {
	Classes(ctx context.Context) (models.Classes, error)
	Races(ctx context.Context) (models.Races, error)
	Backgrounds(ctx context.Context) (models.Backgrounds, error)
	Skills(ctx context.Context) (models.Skills, error)
}

type dndService struct {
	classes     models.Classes
	backgrounds models.Backgrounds
	races       models.Races
	skills      models.Skills
}

func NewDndService(repo CatalogRepository) (*dndService, error) {
	ctx := context.Background()

	classes, err := repo.Classes(ctx)
	if err != nil {
		return nil, err
	}

	races, err := repo.Races(ctx)
	if err != nil {
		return nil, err
	}

	bgs, err := repo.Backgrounds(ctx)
	if err != nil {
		return nil, err
	}

	skills, err := repo.Skills(ctx)
	if err != nil {
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
