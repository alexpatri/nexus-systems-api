package models

import (
	"encoding/json"

	"rpg-nexus/api/dnd/internal/utils"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

type User struct {
	Id       primitive.ObjectID `json:"id" bson:"_id"`
	Name     string             `json:"name" bson:"name"`
	Email    string             `json:"email" bson:"email"`
	Password string             `json:"pass" bson:"pass"`
}

func ConvertJSONToUser(data []byte) (User, error) {
	var user User
	err := json.Unmarshal(data, &user)
	return user, err
}

func NewUserFromJSON(data []byte) (User, error) {
	user, err := ConvertJSONToUser(data)
	if err != nil {
		return User{}, err
	}

	user.Id = primitive.NewObjectID()

	user.Password, err = utils.HashPassword(user.Password)
	if err != nil {
		return User{}, err
	}

	return user, nil
}
