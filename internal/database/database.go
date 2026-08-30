package database

import (
	"context"
	"time"

	"rpg-nexus/api/systems/internal/config"

	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readpref"
)

func Connect(cfg config.DatabaseConfig) (*mongo.Database, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(cfg.URI()))
	if err != nil {
		return nil, err
	}

	// mongo.Connect é lazy: sem o Ping um banco fora só falharia na primeira
	// query, já dentro da montagem do serviço.
	if err := client.Ping(ctx, readpref.Primary()); err != nil {
		return nil, err
	}

	return client.Database(cfg.Name), nil
}
