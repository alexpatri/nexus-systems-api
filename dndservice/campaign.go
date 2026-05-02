package dndservice

import (
    "go.mongodb.org/mongo-driver/bson/primitive"
    "encoding/json"
    "time"
)

type Message struct {
    Text string             `json:"text" bson:"text"`
    Date time.Time          `json:"date" bson:"date"`
}

type Campaign struct {
    Id          primitive.ObjectID  `json:"id,omitempty" bson:"_id,omitempty"`
    Title       string              `json:"title,omitempty" bson:"title,omitempty"`
    Image       string              `json:"img,omitempty" bson:"image,omitempty"`
    Description string              `json:"desc,omitempty" bson:"desc,omitempty"`
    Characters  []Character         `json:"characters" bson:"characters,omitempty"`
    Messages    []Message           `json:"msgs" bson:"msgs,omitempty"`
    Password    string              `json:"-" bson:"pass,omitempty"`
}

func newCampaignFromJSON(data []byte) (Campaign, error) {
    var camp Campaign
    
    err := json.Unmarshal(data, &camp)
    if err != nil {
        return Campaign{}, err
    }

    camp.Id = primitive.NewObjectID()

    camp.Characters = []Character{}
    camp.Messages = []Message{}

    return camp, nil
}
