package models

type Abilities struct {
	Str int `json:"str" bson:"str"`
	Dex int `json:"dex" bson:"dex"`
	Con int `json:"con" bson:"con"`
	Int int `json:"int" bson:"int"`
	Wis int `json:"wis" bson:"wis"`
	Cha int `json:"cha" bson:"cha"`
}
