package models

type Backgrounds struct {
	Docs []Background `json:"backgrounds"`
}

type Background struct {
	Id   string `json:"id" bson:"_id"`
	Name string `json:"name" bson:"background"`
}
