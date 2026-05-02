package models

type Races struct {
	Docs []Race `json:"races"`
}

type Race struct {
	Id    string    `json:"id" bson:"_id"`
	Name  string    `json:"name" bson:"name"`
	Bonus Abilities `json:"bonus" bson:"bonus"`
	Speed string    `json:"speed" bson:"speed"`
	Desc  string    `json:"desc" bson:"desc"`
}
