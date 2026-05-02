package main

import (
	"log"

	"rpg-nexus/api/dnd/internal/api"
	"rpg-nexus/api/dnd/internal/config"
)

func main() {
	cfg := config.LoadConfig()

	app, err := api.NewApp(cfg)
	if err != nil {
		log.Fatalf("falha ao iniciar a aplicação: %v", err)
	}
	log.Fatal(app.Listen(":" + cfg.Server.Port))
}
