// Package fixtures guarda os casos que o core (Go) e o app (TS) rodam para
// calcular igual. Fica fora de data/ para não entrar no binário da API.
package fixtures

import (
	"embed"
	"io/fs"
)

//go:embed shadowrun
var embedded embed.FS

// FS tem caminhos <sistema>/<versão>/…, o mesmo shape de data.Systems().
func FS() fs.FS {
	return embedded
}
