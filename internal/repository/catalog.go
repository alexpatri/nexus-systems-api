package repository

import (
	"context"
	"time"

	"rpg-nexus/api/systems/internal/models"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
)

type Catalog struct {
	db *mongo.Database
}

func NewCatalog(db *mongo.Database) *Catalog {
	return &Catalog{db: db}
}

func (c *Catalog) Classes(ctx context.Context) (models.Classes, error) {
	var out models.Classes
	if err := c.findAll(ctx, "classes", &out.Docs); err != nil {
		return models.Classes{}, err
	}
	return out, nil
}

func (c *Catalog) Races(ctx context.Context) (models.Races, error) {
	var out models.Races
	if err := c.findAll(ctx, "races", &out.Docs); err != nil {
		return models.Races{}, err
	}
	return out, nil
}

func (c *Catalog) Backgrounds(ctx context.Context) (models.Backgrounds, error) {
	var out models.Backgrounds
	if err := c.findAll(ctx, "backgrounds", &out.Docs); err != nil {
		return models.Backgrounds{}, err
	}
	return out, nil
}

func (c *Catalog) Skills(ctx context.Context) (models.Skills, error) {
	var out models.Skills
	if err := c.findAll(ctx, "skills", &out.Docs); err != nil {
		return models.Skills{}, err
	}
	return out, nil
}

func (c *Catalog) findAll(ctx context.Context, collection string, dst any) error {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	cur, err := c.db.Collection(collection).Find(ctx, bson.D{})
	if err != nil {
		return err
	}
	defer cur.Close(ctx)
	return cur.All(ctx, dst)
}
