package models

import (
	"encoding/json"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

type Character struct {
	Id               primitive.ObjectID `json:"id,omitempty" bson:"_id,omitempty"`
	Name             string             `json:"name,omitempty" bson:"name,omitempty"`
	Level            int                `json:"level" bson:"level"`
	MaxHP            int                `json:"maxHP" bson:"maxHP"`
	HP               int                `json:"hp" bson:"hp"`
	TempHP           int                `json:"tempHP" bson:"tempHP"`
	AC               int                `json:"ac" bson:"ac"`
	Speed            string             `json:"speed,omitempty" bson:"speed,omitempty"`
	ProficiencyBonus int                `json:"proficiencyBonus" bson:"proficiencyBonus"`
	Class            Class              `json:"class,omitempty" bson:"class,omitempty"`
	Race             Race               `json:"race,omitempty" bson:"race,omitempty"`
	Background       Background         `json:"background,omitempty" bson:"background,omitempty"`
	Abilities        Abilities          `json:"abilities,omitempty" bson:"abilities,omitempty"`
	Proficiencies    []string           `json:"proficiencies,omitempty" bson:"proficiencies,omitempty"`
}

type Characters struct {
	Docs []Character `json:"characters"`
}

func NewCharacterFromJSON(data []byte) (Character, error) {
	var char Character

	err := json.Unmarshal(data, &char)
	if err != nil {
		return Character{}, err
	}

	char.Id = primitive.NewObjectID()

	char.Abilities = Abilities{
		Str: char.Abilities.Str + char.Race.Bonus.Str,
		Dex: char.Abilities.Dex + char.Race.Bonus.Dex,
		Con: char.Abilities.Con + char.Race.Bonus.Con,
		Int: char.Abilities.Int + char.Race.Bonus.Int,
		Wis: char.Abilities.Wis + char.Race.Bonus.Wis,
		Cha: char.Abilities.Cha + char.Race.Bonus.Cha,
	}

	char.Level = 1
	char.MaxHP = char.Class.HPDice + ((char.Abilities.Con - 10) / 2)
	char.HP = char.MaxHP
	char.AC = 10 + ((char.Abilities.Dex - 10) / 2)
	char.Speed = char.Race.Speed
	char.ProficiencyBonus = 2

	return char, nil
}
