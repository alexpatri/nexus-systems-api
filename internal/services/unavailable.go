package services

import "github.com/gofiber/fiber/v3"

// DndHandlers permite ao router registrar as mesmas rotas com ou sem banco,
// decidindo a implementação uma única vez no boot.
type DndHandlers interface {
	GetClassesHandler(fiber.Ctx) error
	GetRacesHandler(fiber.Ctx) error
	GetBackgroundsHandler(fiber.Ctx) error
	GetSkillsHandler(fiber.Ctx) error
}

type unavailable struct{ reason string }

func Unavailable(reason string) DndHandlers { return unavailable{reason: reason} }

func (u unavailable) fail() error {
	return fiber.NewError(fiber.StatusServiceUnavailable, "catálogos dnd/5e indisponíveis: "+u.reason)
}

func (u unavailable) GetClassesHandler(fiber.Ctx) error     { return u.fail() }
func (u unavailable) GetRacesHandler(fiber.Ctx) error       { return u.fail() }
func (u unavailable) GetBackgroundsHandler(fiber.Ctx) error { return u.fail() }
func (u unavailable) GetSkillsHandler(fiber.Ctx) error      { return u.fail() }
