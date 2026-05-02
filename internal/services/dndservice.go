package services

import (
	"encoding/json"

	"rpg-nexus/api/dnd/internal/database"
	"rpg-nexus/api/dnd/internal/models"
	"rpg-nexus/api/dnd/internal/utils"

	"github.com/gofiber/fiber/v3"
)

type dndService struct {
	dataBase    *database.DataBase
	classes     models.Classes
	backgrounds models.Backgrounds
	races       models.Races
	skills      models.Skills
}

func NewDndService() (*dndService, error) {
	mongoURL := "mongodb://127.0.0.1:27017/"
	db, err := database.NewMongoDB(mongoURL, "dndSheets")
	if err != nil {
		return nil, err
	}

	var classes models.Classes
	err = db.Find("classes", struct{}{}, &classes.Docs)
	if err != nil {
		return nil, err
	}

	var races models.Races
	err = db.Find("races", struct{}{}, &races.Docs)
	if err != nil {
		return nil, err
	}

	var bgs models.Backgrounds
	err = db.Find("backgrounds", struct{}{}, &bgs.Docs)
	if err != nil {
		return nil, err
	}

	var skills models.Skills
	err = db.Find("skills", struct{}{}, &skills.Docs)
	if err != nil {
		return nil, err
	}

	return &dndService{
		dataBase:    db,
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

func (dnd *dndService) GetCharactersHandler(c fiber.Ctx) error {
	var characters models.Characters

	if err := dnd.dataBase.Find("character", struct{}{}, &characters.Docs); err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "Erro interno ao buscar personagens.",
		})
	}

	return c.JSON(characters)
}

func (dnd *dndService) GetCharacterHandler(c fiber.Ctx) error {
	var character models.Character

	if err := dnd.dataBase.FindOneByID("character", c.Params("id"), &character); err != nil {
		if database.IsErrNoDocuments(err) {
			return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
				"error": "Personagem não encontrado.",
			})
		}

		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "Erro interno ao buscar o personagem.",
		})
	}

	return c.JSON(character)
}

func (dnd *dndService) PostCharacterHandler(c fiber.Ctx) error {
	character, err := models.NewCharacterFromJSON(c.Body())
	if err != nil {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "Formato JSON inválido para o personagem.",
		})
	}

	if _, err := dnd.dataBase.InsertOne("character", character); err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "Erro interno ao salvar o personagem.",
		})
	}

	return c.Status(fiber.StatusCreated).JSON(fiber.Map{
		"id": character.Id,
	})
}

func (dnd *dndService) PutCharacterHandler(c fiber.Ctx) error {
	var character models.Character

	if err := json.Unmarshal(c.Body(), &character); err != nil {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "Formato JSON inválido para o personagem.",
		})
	}

	if err := dnd.dataBase.UpdateByID("character", c.Params("id"), character); err != nil {
		if database.IsErrNoDocuments(err) {
			return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
				"error": "Personagem não encontrado.",
			})
		}

		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "Erro interno ao atualizar o personagem.",
		})
	}

	return c.SendStatus(fiber.StatusOK)
}

func (dnd *dndService) DeleteCharacterHandler(c fiber.Ctx) error {
	if err := dnd.dataBase.DeleteByID("character", c.Params("id")); err != nil {
		if database.IsErrNoDocuments(err) {
			return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
				"error": "Personagem não encontrado.",
			})
		}

		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "Erro interno ao excluir o personagem.",
		})
	}

	return c.SendStatus(fiber.StatusNoContent)
}

func (dnd *dndService) CreateCampaignHandler(c fiber.Ctx) error {
	campaign, err := models.NewCampaignFromJSON(c.Body())
	if err != nil {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "Erro ao parsear o JSON da requisição"})
	}

	password, err := utils.GeneratePassword(6, 2, 0)
	if err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Erro ao gerar a senha"})
	}

	hashedPassword, err := utils.HashPassword(password)
	if err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Erro ao gerar o hash da senha"})
	}

	campaign.Password = hashedPassword

	result, err := dnd.dataBase.InsertOne("campaign", campaign)
	if err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Erro ao inserir a campanha no banco de dados"})
	}

	campaignID := result.InsertedID

	return c.Status(fiber.StatusCreated).JSON(fiber.Map{
		"id":   campaignID,
		"pass": password,
	})
}

func (dnd *dndService) GetCampaignsHandler(c fiber.Ctx) error {
	var campaigns []models.Campaign

	err := dnd.dataBase.Find("campaign", struct{}{}, &campaigns)
	if err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Algo deu errado"})
	}

	return c.JSON(fiber.Map{"campaigns": campaigns})
}

func (dnd *dndService) GetCampaignHandler(c fiber.Ctx) error {
	id := c.Params("id")
	if id == "" {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "ID do parâmetro é obrigatório"})
	}

	var body struct {
		Password string `json:"pass"`
	}

	if err := json.Unmarshal(c.Body(), &body); err != nil {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "Body inválido"})
	}

	var campaign models.Campaign
	err := dnd.dataBase.FindOneByID("campaign", id, &campaign)
	if err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Algo deu errado"})
	}

	if !utils.VerifyPassword(body.Password, campaign.Password) {
		return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{"error": "Senha incorreta"})
	}

	if campaign.Characters == nil {
		campaign.Characters = []models.Character{}
	}

	if campaign.Messages == nil {
		campaign.Messages = []models.Message{}
	}

	return c.JSON(campaign)
}

func (dnd *dndService) PutCampaignHandler(c fiber.Ctx) error {
	var campaign models.Campaign

	if err := json.Unmarshal(c.Body(), &campaign); err != nil {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "Formato JSON inválido para a campanha.",
		})
	}

	if err := dnd.dataBase.UpdateByID("campaign", c.Params("id"), campaign); err != nil {
		if database.IsErrNoDocuments(err) {
			return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
				"error": "Campanha não encontrada.",
			})
		}

		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "Erro interno ao atualizar a campanha.",
		})
	}

	return c.SendStatus(fiber.StatusOK)
}

func (dnd *dndService) DeleteCampaignHandler(c fiber.Ctx) error {
	if err := dnd.dataBase.DeleteByID("campaign", c.Params("id")); err != nil {
		if database.IsErrNoDocuments(err) {
			return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
				"error": "Campanha não encontrada.",
			})
		}

		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "Erro interno ao excluir a campanha.",
		})
	}

	return c.SendStatus(fiber.StatusNoContent)
}
