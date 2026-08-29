package data

import (
	"embed"
	"io/fs"
)

//go:embed all:systems
var embedded embed.FS

// Systems enraíza a FS em "systems" para que os caminhos sejam
// <sistema>/<versao>/<arquivo>, o mesmo shape que os testes montam.
func Systems() fs.FS {
	sub, err := fs.Sub(embedded, "systems")
	if err != nil {
		panic(err)
	}
	return sub
}
