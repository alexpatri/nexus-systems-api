package main

import (
	"log"

	"rpg-nexus/api/systems/internal/api"
	"rpg-nexus/api/systems/internal/config"
)

func main() {
	cfg := config.LoadConfig()

	app, err := api.NewApp()
	if err != nil {
		log.Fatalf("falha ao iniciar a aplicação: %v", err)
	}

	log.Fatal(app.Listen(":" + cfg.Server.Port))
}
