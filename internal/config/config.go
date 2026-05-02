package config

import (
	"errors"
	"fmt"
	"io/fs"
	"log"
	"strings"

	"github.com/caarlos0/env/v11"
	"github.com/joho/godotenv"
)

type DatabaseConfig struct {
	Driver   string `env:"DRIVER" envDefault:"mongodb+srv"`
	Host     string `env:"HOST"`
	Port     string `env:"PORT" envDefault:"27017"`
	Name     string `env:"NAME" envDefault:"dnd-api"`
	User     string `env:"USER"`
	Password string `env:"PASSWORD"`
}

func (d DatabaseConfig) URI() string {
	host := d.Host
	if !strings.HasSuffix(d.Driver, "+srv") && d.Port != "" {
		host = fmt.Sprintf("%s:%s", d.Host, d.Port)
	}

	if d.User != "" {
		return fmt.Sprintf("%s://%s:%s@%s/", d.Driver, d.User, d.Password, host)
	}

	return fmt.Sprintf("%s://%s/", d.Driver, host)
}

type ServerConfig struct {
	Port string `env:"PORT" envDefault:"8080"`
}

type Config struct {
	DB     DatabaseConfig `envPrefix:"DB_"`
	Server ServerConfig   `envPrefix:"SERVER_"`
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
