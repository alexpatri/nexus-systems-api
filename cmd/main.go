package main

import (
	"log"

	"rpg-nexus/api/systems/data"
	"rpg-nexus/api/systems/internal/api"
	"rpg-nexus/api/systems/internal/config"
	"rpg-nexus/api/systems/internal/handler"
	"rpg-nexus/api/systems/internal/registry"
)

func main() {
	cfg := config.LoadConfig()

	reg, err := registry.Load(data.Systems())
	if err != nil {
		log.Fatalf("falha ao carregar os sistemas: %v", err)
	}

	app := api.NewApp(handler.New(reg))

	log.Fatal(app.Listen(":" + cfg.Server.Port))
}
