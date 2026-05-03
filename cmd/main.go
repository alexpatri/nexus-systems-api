package main

import (
	"log"

	"rpg-nexus/api/dnd/internal/api"
	"rpg-nexus/api/dnd/internal/config"
	"rpg-nexus/api/dnd/internal/database"
)

func main() {
	cfg := config.LoadConfig()

	db, err := database.Connect(cfg.DB)
	if err != nil {
		log.Fatalf("falha ao conectar ao banco: %v", err)
	}

	app, err := api.NewApp(db)
	if err != nil {
		log.Fatalf("falha ao iniciar a aplicação: %v", err)
	}

	log.Fatal(app.Listen(":" + cfg.Server.Port))
}
