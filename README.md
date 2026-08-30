# Nexus — API de Sistemas

Serve os catálogos de regras dos sistemas de RPG suportados pelo Nexus.

## Rotas

| Rota | Descrição |
| --- | --- |
| `GET /api` | Sistemas e versões disponíveis, com origem e disponibilidade |
| `GET /api/{sistema}/{versao}` | Manifesto do sistema |
| `GET /api/{sistema}/{versao}/{catalogo}` | Um catálogo; o sufixo `.json` é opcional |
| `GET /health` | Responde 200 sempre; o corpo diz se o MongoDB está de pé |

```
GET /api/vileborn/v1/heritages
GET /api/dnd/5e/classes
```

A versão é a edição do sistema, não do contrato HTTP — por isso `v1` no Vileborn e
`5e` no D&D. É string livre: não presuma o prefixo `v`.

Catálogos embutidos respondem com `ETag` e honram `If-None-Match`.

## De onde vêm os dados

Cada sistema é um diretório em `data/systems/{sistema}/{versao}/`, embutido no
binário com `go:embed`. O `system.json` é o manifesto e lista os demais catálogos.

O D&D é a exceção: os catálogos ainda vêm do MongoDB, e o manifesto dele traz
`"catalogSource": "mongo"`. Se o banco não subir, o serviço sobe assim mesmo e só
as rotas do D&D respondem 503.

## Adicionar um sistema

1. Crie `data/systems/{id}/{versao}/system.json` com `id` e `apiVersion` batendo
   com os nomes dos diretórios, e `catalogs` listando os arquivos.
2. Ponha os catálogos no mesmo diretório.
3. `python3 tools/validate.py && go test ./...`

Não há código a escrever: o registry descobre o sistema no boot. Divergência entre
manifesto e diretório, catálogo declarado e ausente, ou catálogo presente e não
declarado derrubam o boot em vez de virar erro na primeira request.
