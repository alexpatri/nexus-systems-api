package models

type Classes struct {
	Docs []Class `json:"classes"`
}

type Proficency struct {
	Qtd    int     `json:"qtd" bson:"qtd"`
	Skills []Skill `json:"skills" bson:"skills"`
}

type Class struct {
	Id         string     `json:"id" bson:"_id"`
	Name       string     `json:"name" bso:"name"`
	HPDice     int        `json:"hpDice" bson:"hpDice"`
	Saving     []string   `json:"saving" bson:"saving"`
	Proficency Proficency `json:"proficiency" bson:"proficency"`
}
