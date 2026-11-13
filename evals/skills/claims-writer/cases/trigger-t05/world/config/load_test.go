package config

import "testing"

func TestMissingFileNamesPath(t *testing.T) {
	if _, err := Load("nope.json"); err == nil {
		t.Fatal("want an error")
	}
}
