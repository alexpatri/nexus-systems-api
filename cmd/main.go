package main

import (
	"log"

	"rpg-nexus/api/systems/internal/api"
	"rpg-nexus/api/systems/internal/config"
	"rpg-nexus/api/systems/internal/database"
)

func main() {
	cfg := config.LoadConfig()

	db, err := database.Connect(cfg.DB)
	if err != nil {
		log.Printf("aviso: mongodb indisponível, catálogos dnd/5e responderão 503: %v", err)
	}

	app, err := api.NewApp(db)
	if err != nil {
		log.Fatalf("falha ao iniciar a aplicação: %v", err)
	}

	log.Fatal(app.Listen(":" + cfg.Server.Port))
}
