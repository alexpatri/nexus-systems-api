package userservice

import (
    "alexsandro/ps-back-end-alexsandro-junior/mongo"
    "alexsandro/ps-back-end-alexsandro-junior/utils"
    "github.com/gofiber/fiber/v3"
)

type userService struct {
    dataBase *mongo.DataBase
}

func NewUserService () (*userService, error) {
    mongoURL := "mongodb://127.0.0.1:27017/"
    db, err := mongo.NewMongoDB(mongoURL, "dndSheets")
    if err != nil {
        return nil, err
    }

    return &userService{
        dataBase: db,
    }, nil
}

func (service *userService) CreateUserHandler(c fiber.Ctx) error {
    user, err := newUserFromJSON(c.Body())
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
    user, err := convertJSONToUser(c.Body())
    if err != nil {
        return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error":"Algo deu errado"})
    }

    filter := mongo.ConvertMapToBson(map[string]string{"email":user.Email})

    var userToCompare User
    err = service.dataBase.FindOne("user", filter, &userToCompare)
    if mongo.IsErrNoDocuments(err) {
        return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error":"Email ou senha incorretos"})
    }

    if err != nil {
       return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error":"Algo deu errado"})
    }

    if !utils.VerifyPassword(user.Password, userToCompare.Password) {
        return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error":"Email ou senha incorretos"})
    }

    return c.Status(fiber.StatusOK).JSON(fiber.Map{"message": "Usuário Encontrado"})
}

func (service *userService) isEmailExists(email string) (bool, error) {
    filter := mongo.ConvertMapToBson(map[string]string{"email":email})

    var user User

    err := service.dataBase.FindOne("user", filter, &user)
    if mongo.IsErrNoDocuments(err) {
        return false, nil
    }
    if err != nil {
       return false, err
    }

    return true, nil
}
