package services

import (
	"rpg-nexus/api/dnd/internal/database"
	"rpg-nexus/api/dnd/internal/models"
	"rpg-nexus/api/dnd/internal/utils"

	"github.com/gofiber/fiber/v3"
)

type userService struct {
	dataBase *database.DataBase
}

func NewUserService() (*userService, error) {
	mongoURL := "mongodb://127.0.0.1:27017/"
	db, err := database.NewMongoDB(mongoURL, "dndSheets")
	if err != nil {
		return nil, err
	}

	return &userService{
		dataBase: db,
	}, nil
}

func (service *userService) CreateUserHandler(c fiber.Ctx) error {
	user, err := models.NewUserFromJSON(c.Body())
	if err != nil {
		return err
	}

	exists, err := service.isEmailExists(user.Email)
	if err != nil {
		return err
	}
	if exists {
		return c.Status(fiber.StatusConflict).JSON(fiber.Map{"error": "Email já cadastrado. Utilize outro email ou faça login"})
	}

	_, err = service.dataBase.InsertOne("user", user)
	return err
}

func (service *userService) ValidateUserHandler(c fiber.Ctx) error {
	user, err := models.ConvertJSONToUser(c.Body())
	if err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Algo deu errado"})
	}

	filter := database.ConvertMapToBson(map[string]string{"email": user.Email})

	var userToCompare models.User
	err = service.dataBase.FindOne("user", filter, &userToCompare)
	if database.IsErrNoDocuments(err) {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "Email ou senha incorretos"})
	}

	if err != nil {
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Algo deu errado"})
	}

	if !utils.VerifyPassword(user.Password, userToCompare.Password) {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "Email ou senha incorretos"})
	}

	return c.Status(fiber.StatusOK).JSON(fiber.Map{"message": "Usuário Encontrado"})
}

func (service *userService) isEmailExists(email string) (bool, error) {
	filter := database.ConvertMapToBson(map[string]string{"email": email})

	var user models.User

	err := service.dataBase.FindOne("user", filter, &user)
	if database.IsErrNoDocuments(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}

	return true, nil
}
