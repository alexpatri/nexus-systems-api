package database

import (
	"context"
	"time"

	"rpg-nexus/api/dnd/internal/config"

	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func Connect(cfg config.DatabaseConfig) (*mongo.Database, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(cfg.URI()))
	if err != nil {
		return nil, err
	}

	return client.Database(cfg.Name), nil
}
