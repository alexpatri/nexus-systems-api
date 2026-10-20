#!/usr/bin/env python3
"""Extrai os catálogos de Shadowrun 5e do Livro Básico em PDF (edição New Order).

Uso: python3 tools/extract_sr5.py [caminho-do-pdf]

Como no extrator de D&D, o vocabulário abaixo é o contrato: o PDF é a fonte do
texto em PT-BR e dos números, mas ids, estrutura e fórmulas são fixos. Entrada
esperada que não for encontrada, ou número que divergir do livro, aborta a
extração em vez de gerar um catálogo silenciosamente errado.

As fórmulas são árvores {"op": ..., "of": [...]} com folhas numéricas ou
{"ref": ...}; o validate.py tem o avaliador de referência.
"""
import json
import pathlib
import re
import sys

from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "systems" / "shadowrun" / "5e"
DEFAULT_PDF = pathlib.Path.home() / "Downloads" / "ShadowRun-5_327757_1791423088.pdf"


class ExtractionError(Exception):
    pass


# --- fórmulas ---

def ref(name):
    return {"ref": name}


def op(name, *args):
    return {"op": name, "of": list(args)}


def attr(attr_id):
    return ref(f"attr.{attr_id}")


def add(*args):
    return op("add", *args)


def mul(*args):
    return op("mul", *args)


def div(a, b):
    return op("div", a, b)


def ceil(a):
    return op("ceil", a)


def floor(a):
    return op("floor", a)


# --- vocabulário ---

ATTRIBUTES = [
    ("bod", "Corpo", "COR", "physical", "CORPO (COR)"),
    ("agi", "Agilidade", "AGI", "physical", "AGILIDADE (AGI)"),
    ("rea", "Reação", "REA", "physical", "REAÇÃO (REA)"),
    ("str", "Força", "FOR", "physical", "FORÇA (FOR)"),
    ("wil", "Vontade", "VON", "mental", "VONTADE (VON)"),
    ("log", "Lógica", "LÓG", "mental", "LÓGICA (LOG)"),
    ("int", "Intuição", "INT", "mental", "INTUIÇÃO (INT)"),
    ("cha", "Carisma", "CAR", "mental", "CARISMA (CAR)"),
    ("ess", "Essência", "ESS", "special", "ESSÊNCIA (ESS)"),
    ("edg", "Trunfo", "TRU", "special", "TRUNFO (TRU)"),
    ("mag", "Magia", "MAG", "special", "MAGIA (MAG)"),
    ("res", "Ressonância", "RES", "special", "RESSONÂNCIA (RES)"),
]
ATTRIBUTE_NAMES = {a[0]: a[1] for a in ATTRIBUTES}
# Ordem das colunas na Tabela de Atributo de Metatipo (p. 66).
METATYPE_COLUMNS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha", "edg"]

METATYPES = [
    ("human", "Humano", "Humano"),
    ("elf", "Elfo", "Elfos"),
    ("dwarf", "Anão", "Anões"),
    ("ork", "Ork", "Orks"),
    ("troll", "Troll", "Trolls"),
]

RACIAL_TRAITS = {
    "Visão na Penumbra": {"id": "low-light-vision"},
    "Visão Termográfica": {"id": "thermographic-vision"},
    "+2 dados para resistência a patogênicos e toxinas": {"id": "pathogen-toxin-resistance"},
    "+1 de Alcance": {"id": "reach", "modifiers": [{"target": "reach", "add": 1}]},
    "+1 de armadura dérmica": {"id": "dermal-armor", "modifiers": [{"target": "armor", "add": 1}]},
    "+20% de aumento no custo de Estilo de Vida":
        {"id": "lifestyle-cost", "modifiers": [{"target": "lifestyle.cost", "mul": 1.2}]},
    "+100% de aumento no custo de Estilo de Vida":
        {"id": "lifestyle-cost", "modifiers": [{"target": "lifestyle.cost", "mul": 2}]},
}

SPRINT = {"dwarf": 1, "troll": 1, "elf": 2, "human": 2, "ork": 2}

AWAKENINGS = [
    ("magician", "Mago", "mag", "MAGOS"),
    ("mystic-adept", "Adepto Místico", "mag", "ADEPTOS MÍSTICOS"),
    ("adept", "Adepto", "mag", "ADEPTOS"),
    ("aspected-magician", "Mago Aspectado", "mag", "MAGOS ASPECTADOS"),
    ("technomancer", "Tecnomante", "res", None),
]


# --- leitura do livro ---

WATERMARK = re.compile(r'^Licenciado para .*$', re.M)
# Cabeçalhos e rodapés correntes: ">> CAPÍTULO <<", "<< SEÇÃO    65", "66    SEÇÃO >>".
RUNNING = re.compile(r'^\s*(?:>>.*<<|<<.*\s\d+|\d+\s{2,}.*>>|SEÇÃO\.\d+|SHADOWRUN LIVRO BÁSICO\s+\d+)\s*$', re.M)
SOFT_BREAK = re.compile(r'(\w+) ?-\n(\w+)')
INLINE_HYPHEN = re.compile(r'\b\w+-\w+\b')


class Book:
    """As páginas do PDF coincidem com a numeração impressa: page(65) é a 65."""

    def __init__(self, path):
        self._pages = PdfReader(str(path)).pages
        self._cache = {}
        self._hyphenated = None

    def page(self, n):
        if n not in self._cache:
            raw = self._pages[n - 1].extract_text() or ""
            raw = WATERMARK.sub("", raw)
            raw = RUNNING.sub("", raw)
            self._cache[n] = "\n".join(line.rstrip() for line in raw.split("\n") if line.strip())
        return self._cache[n]

    def text(self, first, last):
        return "\n".join(self.page(p) for p in range(first, last + 1))

    def hyphenated(self):
        """Palavras que o livro escreve com hífen no meio da linha."""
        if self._hyphenated is None:
            words = set()
            for n in range(1, len(self._pages) + 1):
                text = SOFT_BREAK.sub(" ", self.page(n))
                words.update(w.lower() for w in INLINE_HYPHEN.findall(text))
            self._hyphenated = words
        return self._hyphenated

    def prose(self, text):
        """Junta as linhas de um trecho, desfazendo a hifenização da diagramação."""
        def join(m):
            word = f"{m.group(1)}-{m.group(2)}"
            return word if word.lower() in self.hyphenated() else m.group(1) + m.group(2)
        text = SOFT_BREAK.sub(join, text)
        text = " ".join(text.split())
        text = re.sub(r'\bp\. ?(\d) (\d\d)\b', r'p. \1\2', text)
        text = re.sub(r'\(\s+', '(', text)
        text = re.sub(r'\s+([),.;:!?])', r'\1', text)
        return text


def section(text, start, stops):
    """Trecho entre um marcador (texto ou regex compilada) e o primeiro dos seguintes."""
    if isinstance(start, re.Pattern):
        m = start.search(text)
        if not m:
            return None
        rest = text[m.end():]
    else:
        i = text.find(start)
        if i < 0:
            return None
        rest = text[i + len(start):]
    ends = [m.start() for p in stops for m in [re.search(p, rest, re.M)] if m]
    return rest[:min(ends)] if ends else rest


def require(text, fragment, where):
    if fragment not in text:
        raise ExtractionError(f"{where}: trecho esperado não encontrado: {fragment!r}")


def split_list(text):
    """Divide por vírgula fora de parênteses."""
    out, depth, cur = [], 0, ""
    for c in text:
        depth += (c == "(") - (c == ")")
        if c == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += c
    out.append(cur)
    return [s.strip().rstrip(".").strip() for s in out if s.strip()]


# --- construtores ---

def build_attributes(book):
    text = book.text(51, 52)
    headings = [a[4] for a in ATTRIBUTES]
    stops = [re.escape(h) for h in headings] + [r'ATRIBUTOS MENTAIS', r'ATRIBUTOS ESPECIAIS',
                                                r'INICIATIVA E MONITORES']
    out = []
    for attr_id, name, abbr, category, heading in ATTRIBUTES:
        body = section(text, heading, stops)
        if not body:
            raise ExtractionError(f"atributo {name}: cabeçalho {heading!r} não encontrado")
        out.append({"id": attr_id, "name": name, "abbr": abbr, "category": category,
                    "desc": book.prose(body), "page": 51 if body in book.page(51) else 52})
    return {"attributes": out}


def build_metatypes(book):
    table = book.page(66)
    rows = {}
    for m in re.finditer(r'^(Humano|Elfo|Anão|Ork|Troll) ((?:\d+/\d+ ){9})(\d+) REA \+ INT\s*$', table, re.M):
        pairs = [tuple(map(int, p.split("/"))) for p in m.group(2).split()]
        rows[m.group(1)] = (pairs, int(m.group(3)))
    racials = dict(re.findall(r'^Racial (Humano|Elfo|Anão|Ork|Troll): (.+?)\s*$', table, re.M))

    movement = book.text(162, 163)
    prose = book.text(50, 51)
    labels = [label for _, _, label in METATYPES]
    out = []
    for mid, name, label in METATYPES:
        if name not in rows or name not in racials:
            raise ExtractionError(f"metatipo {name}: linha da Tabela de Atributo de Metatipo não encontrada")
        pairs, essence = rows[name]
        attributes = {a: {"min": lo, "max": hi} for a, (lo, hi) in zip(METATYPE_COLUMNS, pairs)}
        attributes["ess"] = {"start": essence}

        traits = []
        if racials[name] != "Nenhum":
            for item in split_list(racials[name]):
                if item not in RACIAL_TRAITS:
                    raise ExtractionError(f"metatipo {name}: traço racial fora do vocabulário: {item!r}")
                traits.append({"id": RACIAL_TRAITS[item]["id"], "name": item,
                               **({"modifiers": RACIAL_TRAITS[item]["modifiers"]}
                                  if "modifiers" in RACIAL_TRAITS[item] else {})})

        m = re.search(rf'^{label} \(\s*(Homo sapiens \w+)\s*\)', prose, re.M)
        if not m:
            raise ExtractionError(f"metatipo {name}: parágrafo de descrição não encontrado")
        rest = prose[m.start():]
        others = [rf'^{other} \(\s*Homo' for other in labels if other != label] + [r'^ATRIBUTOS$']
        ends = [x.start() for p in others for x in [re.search(p, rest, re.M)] if x]
        body = rest[:min(ends)] if ends else rest
        body = "\n".join(line for line in body.split("\n")
                         if line.strip() not in {"HUMANO", "ORK", "TROLL", "ELFO", "ANÃO"})

        sprint_names = {"dwarf": "Anão, Troll", "troll": "Anão, Troll",
                        "elf": "Elfo, Humano, Ork", "human": "Elfo, Humano, Ork", "ork": "Elfo, Humano, Ork"}[mid]
        require(movement, f"{sprint_names} Agilidade x 2 Agilidade x 4 +{SPRINT[mid]} m/sucesso",
                f"metatipo {name}")

        out.append({"id": mid, "name": name, "species": m.group(1), "attributes": attributes,
                    "traits": traits, "sprintPerHit": SPRINT[mid], "desc": book.prose(body), "page": 50})
    return {"metatypes": out}


def magic_user(awakening, mag, skills, formulas):
    grant = {"awakening": awakening, "attribute": {"id": "mag", "value": mag}}
    if skills:
        grant["skills"] = {"count": 2, "rating": skills, "from": {"attribute": "mag"}}
    grant["formulas"] = formulas
    return grant


TECHNO_NOTE = ("O exemplo da p. 70 diverge da tabela (duas perícias e 2 formas complexas na "
               "prioridade B); vale a tabela.")


def technomancer(res, rating, forms):
    return {"awakening": "technomancer", "attribute": {"id": "res", "value": res},
            "skills": {"count": 3, "rating": rating, "from": {"groups": ["tasking", "electronics", "cracking"]}},
            "complexForms": forms, "note": TECHNO_NOTE}


def adept(mag, rating=None):
    grant = {"awakening": "adept", "attribute": {"id": "mag", "value": mag}}
    if rating:
        grant["skills"] = {"count": 1, "rating": rating, "from": {"kind": "active"}}
    return grant


def aspected(mag, rating=None):
    grant = {"awakening": "aspected-magician", "attribute": {"id": "mag", "value": mag}}
    if rating:
        grant["skillGroups"] = {"count": 1, "rating": rating,
                                "from": {"groups": ["sorcery", "conjuring", "enchanting"]}}
    return grant


PRIORITIES = [
    ("A", [("human", 9), ("elf", 8), ("dwarf", 7), ("ork", 7), ("troll", 5)], 24,
     [magic_user("magician", 6, 5, 10), magic_user("mystic-adept", 6, 5, 10), technomancer(6, 5, 7)],
     (46, 10), 450000,
     ["Mago ou Adepto Místico: Magia 6, duas perícias Mágicas em Nível 5, 10 feitiços",
      "Tecnomante: Ressonância 6, três perícias de Ressonância em Nível 5", "7 formas complexas"]),
    ("B", [("human", 7), ("elf", 6), ("dwarf", 4), ("ork", 4), ("troll", 0)], 20,
     [magic_user("magician", 4, 4, 7), magic_user("mystic-adept", 4, 4, 7), technomancer(4, 4, 4),
      adept(6, 4), aspected(5, 4)],
     (36, 5), 275000,
     ["Mago ou Adepto Místico: Magia 4, duas perícias Mágicas em Nível 4, 7 feitiços",
      "Tecnomante: Ressonância 4, três perícias em Nível 4", "4 formas complexas",
      "Adepto: Magia 6, uma perícia Ativa em Nível 4",
      "Mago Aspectado: Magia 5, um grupo de perícias de Magia em Nível 4"]),
    ("C", [("human", 5), ("elf", 3), ("dwarf", 1), ("ork", 0)], 16,
     [magic_user("magician", 3, None, 5), magic_user("mystic-adept", 3, None, 5), technomancer(3, 2, 3),
      adept(4, 2), aspected(3, 2)],
     (28, 2), 140000,
     ["Mago ou Adepto Místico: Magia 3, 5 feitiços", "Tecnomante: Ressonância 3, três perícias em Nível 2",
      "3 forma complexa", "Adepto: Magia 4, uma perícia Ativa em Nível 2",
      "Mago Aspectado: Magia 3, um grupo de perícias de Magia em Nível 2"]),
    ("D", [("human", 3), ("elf", 0)], 14, [adept(2), aspected(2)], (22, 0), 50000,
     ["Adepto: Magia 2", "Mago Aspectado: Magia 2"]),
    ("E", [("human", 1)], 12, [], (18, 0), 6000, []),
]

COLUMNS = [("metatype", "Metatipo"), ("attributes", "Atributos"), ("magic", "Magia ou Ressonância"),
           ("skills", "Perícias"), ("resources", "Recursos")]


def money(value):
    return f"{value:,}".replace(",", ".") + "¥"


def build_priorities(book):
    text = book.prose(section(book.page(65), "TABELA DE PRIORIDADE", [r'^>>']) or "")
    if not text:
        raise ExtractionError("Tabela de Prioridade não encontrada na p. 65")
    names = {mid: name for mid, name, _ in METATYPES}
    rows = []
    for priority, metatypes, attributes, magic, (skills, groups), resources, fragments in PRIORITIES:
        # No texto extraído cada linha começa "A Humano (9) Elfo (8) … 24": letra,
        # metatipos e pontos de atributo em sequência.
        row = " ".join([priority] + [f"{names[mid]} ({special})" for mid, special in metatypes] + [str(attributes)])
        require(text, row, f"prioridade {priority}")
        require(text, f"{skills}/{groups} {money(resources)}", f"prioridade {priority}")
        for fragment in fragments:
            require(text, fragment, f"prioridade {priority}")
        rows.append({
            "priority": priority,
            "metatype": [{"metatype": mid, "specialPoints": special} for mid, special in metatypes],
            "attributes": attributes,
            "magic": magic,
            "skills": {"points": skills, "groupPoints": groups},
            "resources": resources,
        })
    return {"columns": [{"id": cid, "name": name} for cid, name in COLUMNS], "rows": rows, "page": 65}


def build_awakening(book):
    text = book.page(69)
    headings = [h for *_, h in AWAKENINGS if h]
    out = []
    for aid, name, attribute, heading in AWAKENINGS:
        entry = {"id": aid, "name": name, "attribute": attribute}
        if heading:
            body = section(text, f"\n{heading}\n", [rf'^{h}$' for h in headings if h != heading]
                           + [r'^VIDA COMO UM TECNOMANTE'])
            if not body:
                raise ExtractionError(f"despertar {name}: seção {heading!r} não encontrada na p. 69")
            bullets = []
            for b in (book.prose(b) for b in re.split(r'^•\s*', body, flags=re.M) if b.strip()):
                # Os três grupos do mago aspectado são subitens do item anterior.
                if b.split(" (")[0] in ("Feitiçaria", "Convocação", "Encantação"):
                    if bullets[-1].endswith("."):
                        bullets[-1] = bullets[-1][:-1] + ":"
                    bullets[-1] += (" " if bullets[-1].endswith(":") else "; ") + b
                else:
                    bullets.append(b)
            entry["rules"] = bullets
            entry["page"] = 69
        else:
            entry["rules"] = []
            entry["page"] = 249
        entry.update(AWAKENING_RULES[aid])
        out.append(entry)

    for fragment in ["Adeptos recebem um número de pontos de poder igual ao seu nível de Magia",
                     "5 de Carma para cada Pontos de Poder completo, com um número máximo de pontos igual ao "
                     "nível de atributo Magia",
                     "igual ao seu Nível de Magia x 2"]:
        require(book.prose(text), fragment, "despertos (p. 69)")
    return {"awakenings": out}


AWAKENING_RULES = {
    "magician": {"astralPerception": True, "astralProjection": True, "magicSkillGroups": "all",
                 "mentorSpirit": True, "formulasMax": mul(attr("mag"), 2)},
    "mystic-adept": {"astralPerception": "adept-power", "astralProjection": False, "magicSkillGroups": "all",
                     "mentorSpirit": True, "formulasMax": mul(attr("mag"), 2),
                     "powerPoints": {"karmaPerPoint": 5, "max": attr("mag")}},
    "adept": {"astralPerception": "adept-power", "astralProjection": False, "magicSkillGroups": "none",
              "mentorSpirit": True, "powerPoints": {"free": attr("mag")}},
    "aspected-magician": {"astralPerception": True, "astralProjection": False, "magicSkillGroups": "one",
                          "mentorSpirit": True, "formulasMax": mul(attr("mag"), 2)},
    "technomancer": {"complexFormsMax": mul(attr("res"), 2)},
}


CATALOGS = {
    "attributes.json": build_attributes,
    "metatypes.json": build_metatypes,
    "priorities.json": build_priorities,
    "awakening.json": build_awakening,
}

EXPECTED_COUNTS = {
    "attributes.json": {"attributes": 12},
    "metatypes.json": {"metatypes": 5},
    "priorities.json": {"rows": 5},
    "awakening.json": {"awakenings": 5},
}


def write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main():
    pdf = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf.exists():
        sys.exit(f"PDF não encontrado: {pdf}")

    book = Book(pdf)
    OUT.mkdir(parents=True, exist_ok=True)

    for filename, builder in CATALOGS.items():
        payload = builder(book)
        for key, count in EXPECTED_COUNTS[filename].items():
            if len(payload[key]) != count:
                sys.exit(f"{filename}: {key} tem {len(payload[key])} itens, esperado {count}")
        dump = json.dumps(payload, ensure_ascii=False)
        if "Licenciado" in dump or "@" in dump:
            sys.exit(f"{filename}: marca d'água do PDF vazou para o catálogo")
        write(OUT / filename, payload)
        counts = EXPECTED_COUNTS[filename]
        print(f"  {filename:<20} {', '.join(f'{len(payload[k])} {k}' for k in counts) or 'ok'}")


if __name__ == "__main__":
    try:
        main()
    except ExtractionError as err:
        sys.exit(f"extração abortada: {err}")
