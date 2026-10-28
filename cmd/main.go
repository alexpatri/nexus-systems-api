package main

import (
	"log"

	"github.com/alexpatri/nexus-systems-api/data"
	"github.com/alexpatri/nexus-systems-api/internal/api"
	"github.com/alexpatri/nexus-systems-api/internal/config"
	"github.com/alexpatri/nexus-systems-api/internal/handler"
	"github.com/alexpatri/nexus-systems-api/internal/registry"
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
