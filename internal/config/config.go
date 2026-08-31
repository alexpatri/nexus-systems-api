package config

import (
	"errors"
	"io/fs"
	"log"

	"github.com/caarlos0/env/v11"
	"github.com/joho/godotenv"
)

type ServerConfig struct {
	Port string `env:"PORT" envDefault:"8080"`
}

type Config struct {
	Server ServerConfig `envPrefix:"SERVER_"`
}

func LoadConfig() *Config {
	if err := godotenv.Load(); err != nil && !errors.Is(err, fs.ErrNotExist) {
		log.Fatalf("erro ao carregar arquivo .env: %v", err)
	}

	var cfg Config

	if err := env.Parse(&cfg); err != nil {
		log.Fatalf("erro ao carregar variáveis de ambiente: %v", err)
	}

	return &cfg
}
