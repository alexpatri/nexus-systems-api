package models

type Skills struct {
	Docs []Skill `json:"skills"`
}

type Skill struct {
	Id      string `json:"id" bson:"_id"`
	Name    string `json:"name" bson:"name"`
	Ability string `json:"ability" bson:"ability"`
}
