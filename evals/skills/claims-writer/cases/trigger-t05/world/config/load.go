package config

import (
	"encoding/json"
	"fmt"
	"os"
)

type Config struct {
	Port int `json:"port"`
}

func Load(path string) (Config, error) {
	var c Config
	data, err := os.ReadFile(path)
	if err != nil {
		return c, fmt.Errorf("config %s: %w", path, err)
	}
	return c, json.Unmarshal(data, &c)
}
