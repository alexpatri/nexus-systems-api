// Package registry serve catálogos de sistemas de RPG como bytes opacos.
// Os sistemas não têm shape em comum, então nada aqui conhece o domínio deles.
package registry

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io/fs"
	"path"
	"sort"
	"strings"
)

const (
	manifestFile = "system.json"
	manifestKey  = "system"

	SourceEmbed = "embed"
	SourceMongo = "mongo"
)

type System struct {
	ID            string
	Version       string
	Name          string
	CatalogSource string
	CatalogNames  []string
	Manifest      json.RawMessage
	ManifestETag  string

	catalogs map[string]json.RawMessage
	etags    map[string]string
}

// Catalog aceita o nome com ou sem o sufixo .json, para que os ponteiros
// entre catálogos possam ser usados como caminho de URL sem tradução.
func (s *System) Catalog(name string) (json.RawMessage, string, bool) {
	key := strings.TrimSuffix(strings.ToLower(name), ".json")
	raw, ok := s.catalogs[key]
	if !ok {
		return nil, "", false
	}
	return raw, s.etags[key], true
}

type Registry struct {
	systems map[string]map[string]*System
}

func (r *Registry) System(id, version string) (*System, bool) {
	versions, ok := r.systems[strings.ToLower(id)]
	if !ok {
		return nil, false
	}
	s, ok := versions[strings.ToLower(version)]
	return s, ok
}

// All devolve os sistemas ordenados: iteração de map é aleatória e o índice
// precisa ser byte-estável entre requests.
func (r *Registry) All() []*System {
	out := make([]*System, 0, len(r.systems))
	for _, versions := range r.systems {
		for _, s := range versions {
			out = append(out, s)
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].ID != out[j].ID {
			return out[i].ID < out[j].ID
		}
		return out[i].Version < out[j].Version
	})
	return out
}

func Load(fsys fs.FS) (*Registry, error) {
	roots, err := fs.ReadDir(fsys, ".")
	if err != nil {
		return nil, fmt.Errorf("registry: %w", err)
	}

	reg := &Registry{systems: make(map[string]map[string]*System, len(roots))}
	for _, root := range roots {
		if !root.IsDir() {
			return nil, fmt.Errorf("registry: %q não é um diretório de sistema", root.Name())
		}

		versions, err := fs.ReadDir(fsys, root.Name())
		if err != nil {
			return nil, fmt.Errorf("registry: %w", err)
		}
		if len(versions) == 0 {
			return nil, fmt.Errorf("registry: sistema %q não tem versões", root.Name())
		}

		for _, v := range versions {
			if !v.IsDir() {
				return nil, fmt.Errorf("registry: %s/%s não é um diretório de versão", root.Name(), v.Name())
			}
			sys, err := loadSystem(fsys, root.Name(), v.Name())
			if err != nil {
				return nil, err
			}
			if reg.systems[sys.ID] == nil {
				reg.systems[sys.ID] = map[string]*System{}
			}
			reg.systems[sys.ID][sys.Version] = sys
		}
	}
	return reg, nil
}

type manifest struct {
	ID            string   `json:"id"`
	Name          string   `json:"name"`
	APIVersion    string   `json:"apiVersion"`
	CatalogSource string   `json:"catalogSource"`
	Catalogs      []string `json:"catalogs"`
}

func loadSystem(fsys fs.FS, id, version string) (*System, error) {
	dir := path.Join(id, version)

	raw, err := fs.ReadFile(fsys, path.Join(dir, manifestFile))
	if err != nil {
		return nil, fmt.Errorf("registry: %s: %w", dir, err)
	}

	var m manifest
	if err := json.Unmarshal(raw, &m); err != nil {
		return nil, fmt.Errorf("registry: %s/%s: %w", dir, manifestFile, err)
	}
	if !strings.EqualFold(m.ID, id) {
		return nil, fmt.Errorf("registry: %s: manifesto declara id %q", dir, m.ID)
	}
	// Sem isto, um `cp -r v1 v2` esquecido serviria a v1 sob a URL da v2.
	if !strings.EqualFold(m.APIVersion, version) {
		return nil, fmt.Errorf("registry: %s: manifesto declara apiVersion %q", dir, m.APIVersion)
	}

	source := m.CatalogSource
	if source == "" {
		source = SourceEmbed
	}

	sys := &System{
		ID:            strings.ToLower(id),
		Version:       strings.ToLower(version),
		Name:          m.Name,
		CatalogSource: source,
		CatalogNames:  m.Catalogs,
		Manifest:      raw,
		ManifestETag:  etag(raw),
		catalogs:      map[string]json.RawMessage{manifestKey: raw},
		etags:         map[string]string{manifestKey: etag(raw)},
	}

	declared := make(map[string]bool, len(m.Catalogs))
	for _, name := range m.Catalogs {
		declared[name] = true
	}

	entries, err := fs.ReadDir(fsys, dir)
	if err != nil {
		return nil, fmt.Errorf("registry: %w", err)
	}
	for _, e := range entries {
		if e.IsDir() {
			return nil, fmt.Errorf("registry: %s: nível extra %q", dir, e.Name())
		}
		name := e.Name()
		if name == manifestFile || !strings.HasSuffix(name, ".json") {
			continue
		}
		// Um catálogo não declarado seria servido em silêncio, ou não seria
		// servido de jeito nenhum — nos dois casos sem sinal de erro.
		if !declared[name] {
			return nil, fmt.Errorf("registry: %s: %s não está declarado em catalogs", dir, name)
		}
		body, err := fs.ReadFile(fsys, path.Join(dir, name))
		if err != nil {
			return nil, fmt.Errorf("registry: %w", err)
		}
		key := strings.TrimSuffix(name, ".json")
		sys.catalogs[key] = body
		sys.etags[key] = etag(body)
	}

	if source == SourceEmbed {
		for _, name := range m.Catalogs {
			if _, _, ok := sys.Catalog(name); !ok {
				return nil, fmt.Errorf("registry: %s: catálogo declarado e ausente: %s", dir, name)
			}
		}
	}

	return sys, nil
}

func etag(b []byte) string {
	sum := sha256.Sum256(b)
	return `"` + hex.EncodeToString(sum[:]) + `"`
}
