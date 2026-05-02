package userservice

import (
    "alexsandro/ps-back-end-alexsandro-junior/utils"
    "encoding/json"
    "go.mongodb.org/mongo-driver/bson/primitive"
)

type User struct{
    Id  primitive.ObjectID  `json:"id" bson:"_id"`
    Name string             `json:"name" bson:"name"`
    Email string            `json:"email" bson:"email"`
    Password string         `json:"pass" bson:"pass"`
}

func convertJSONToUser(data []byte) (User, error) {
    var user User
    err := json.Unmarshal(data, &user)
    return user, err
}

func newUserFromJSON(data []byte) (User, error) {
    user, err := convertJSONToUser(data)
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
