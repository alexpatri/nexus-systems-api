package main

import (
	"log"

	"rpg-nexus/api/dnd/internal/api"
)

func main() {
	app, err := api.NewApp()
	if err != nil {
		log.Fatalf("falha ao iniciar a aplicação: %v", err)
	}
	log.Fatal(app.Listen(":8080"))
}
