# Nexus — API de Sistemas

Serve os catálogos de regras dos sistemas de RPG suportados pelo Nexus.

## Rotas

| Rota | Descrição |
| --- | --- |
| `GET /api` | Sistemas e versões disponíveis, com os catálogos de cada um |
| `GET /api/{sistema}/{versao}` | Manifesto do sistema |
| `GET /api/{sistema}/{versao}/{catalogo}` | Um catálogo; o sufixo `.json` é opcional |
| `GET /health` | Responde 200 sempre; o corpo traz quantos sistemas foram carregados |

```
GET /api/vileborn/v1/heritages
GET /api/dnd/5e/classes
GET /api/shadowrun/5e/priorities
```

A versão é a edição do sistema, não do contrato HTTP — por isso `v1` no Vileborn e
`5e` no D&D e no Shadowrun. É string livre: não presuma o prefixo `v`.

Catálogos embutidos respondem com `ETag` e honram `If-None-Match`.

## De onde vêm os dados

Cada sistema é um diretório em `data/systems/{sistema}/{versao}/`, embutido no
binário com `go:embed`. O `system.json` é o manifesto e lista os demais catálogos.
O serviço não depende de banco: tudo que ele serve está no binário.

### Fórmulas (Shadowrun)

Valores que a ficha calcula — limites, monitores, iniciativa, Dreno, custos por
Nível — vêm como árvores de expressão, não como texto:

```json
{"op": "ceil", "of": [{"op": "div", "of": [{"ref": "attr.bod"}, 2]}]}
```

Os operadores são `add`, `sub`, `mul`, `div`, `ceil`, `floor`, `min` e `max`; as
folhas são números ou `{"ref": …}`, com as referências listadas em
`mechanics.json#expressions`. O avaliador de referência está em
`tools/validate.py` (`sr_eval`), que também confere as fórmulas contra os
personagens de exemplo do livro.

## Adicionar um sistema

1. Crie `data/systems/{id}/{versao}/system.json` com `id` e `apiVersion` batendo
   com os nomes dos diretórios, e `catalogs` listando os arquivos.
2. Ponha os catálogos no mesmo diretório.
3. `python3 tools/validate.py && go test ./...`

Não há código a escrever: o registry descobre o sistema no boot. Divergência entre
manifesto e diretório, catálogo declarado e ausente, ou catálogo presente e não
declarado derrubam o boot em vez de virar erro na primeira request.
