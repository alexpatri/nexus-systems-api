#!/usr/bin/env python3
"""Extrai os catálogos de D&D 5e do Livro do Jogador em PDF.

Uso: python3 tools/extract_dnd.py [caminho-do-pdf]

O vocabulário controlado abaixo é o contrato: o PDF é a fonte do texto em PT-BR,
mas a estrutura é fixa. Qualquer entrada esperada que não for encontrada aborta a
extração, em vez de gerar um catálogo silenciosamente incompleto.
"""
import json
import pathlib
import re
import sys

from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "systems" / "dnd" / "5e"
DEFAULT_PDF = pathlib.Path.home() / "Downloads" / "LDJ.pdf"

ABILITIES = [
    ("str", "Força"),
    ("dex", "Destreza"),
    ("con", "Constituição"),
    ("int", "Inteligência"),
    ("wis", "Sabedoria"),
    ("cha", "Carisma"),
]

SKILLS = [
    ("athletics", "Atletismo", "str"),
    ("acrobatics", "Acrobacia", "dex"),
    ("sleight-of-hand", "Prestidigitação", "dex"),
    ("stealth", "Furtividade", "dex"),
    ("arcana", "Arcanismo", "int"),
    ("history", "História", "int"),
    ("investigation", "Investigação", "int"),
    ("nature", "Natureza", "int"),
    ("religion", "Religião", "int"),
    ("animal-handling", "Adestrar Animais", "wis"),
    ("insight", "Intuição", "wis"),
    ("medicine", "Medicina", "wis"),
    ("perception", "Percepção", "wis"),
    ("survival", "Sobrevivência", "wis"),
    ("deception", "Enganação", "cha"),
    ("intimidation", "Intimidação", "cha"),
    ("performance", "Atuação", "cha"),
    ("persuasion", "Persuasão", "cha"),
]

SIZES = {"Miúdo", "Pequeno", "Médio", "Grande", "Enorme", "Imenso"}

LANGUAGES = {
    "Comum", "Anão", "Élfico", "Gigante", "Gnômico", "Goblin", "Halfling", "Orc",
    "Abissal", "Celestial", "Dracônico", "Infernal", "Primordial", "Silvestre",
    "Subterrâneo",
}

RACES = [
    {"id": "dwarf", "name": "Anão", "section": "ANÕES", "pages": (20, 22), "subraces": [
        ("hill-dwarf", "Anão da Colina", "ANÃO DA COLINA"),
        ("mountain-dwarf", "Anão da Montanha", "ANÃO DA MONTANHA")]},
    {"id": "elf", "name": "Elfo", "section": "ELFOS", "pages": (23, 27), "subraces": [
        ("high-elf", "Alto Elfo", "ALTO ELFO"),
        ("wood-elf", "Elfo da Floresta", "ELFO DA FLORESTA"),
        ("dark-elf", "Elfo Negro", "ELFO NEGRO")]},
    {"id": "halfling", "name": "Halfling", "section": "HALFLINGS", "pages": (28, 29), "subraces": [
        ("lightfoot", "Pés Leves", "PÉS LEVES"),
        ("stout", "Robusto", "ROBUSTO")]},
    {"id": "human", "name": "Humano", "section": "HUMANOS", "pages": (31, 32), "subraces": []},
    {"id": "dragonborn", "name": "Draconato", "section": "DRACONATOS", "pages": (34, 35), "subraces": []},
    {"id": "gnome", "name": "Gnomo", "section": "GNOMOS", "pages": (36, 38), "subraces": [
        ("forest-gnome", "Gnomo da Floresta", "GNOMO DA FLORESTA"),
        ("rock-gnome", "Gnomo das Rochas", "GNOMO DAS ROCHAS")]},
    {"id": "half-elf", "name": "Meio-Elfo", "section": "MEIO-ELFOS", "pages": (39, 40), "subraces": []},
    {"id": "half-orc", "name": "Meio-Orc", "section": "MEIO-ORCS", "pages": (41, 42), "subraces": []},
    {"id": "tiefling", "name": "Tiefling", "section": "TIEFLINGS", "pages": (43, 44), "subraces": []},
]

STRUCTURAL_TRAITS = {
    "Aumento no Valor de Habilidade", "Idade", "Tendência", "Tamanho",
    "Deslocamento", "Idiomas", "Sub-raça",
}

ABILITY_BY_NAME = {name: ability_id for ability_id, name in ABILITIES}

TRAIT_HEADER = re.compile(
    r'^\s*([A-ZÀ-Ú][\wÀ-ÿ]*(?:[ \-](?:de|do|da|dos|das|no|na|em|com|e|a|ao|aos|à|às)|[ \-][A-ZÀ-Ú][\wÀ-ÿ]*)*)[.:]\s',
    re.M)


ABILITY_CHAPTER = (173, 180)


class ExtractionError(Exception):
    pass


class Book:
    """As páginas do PDF coincidem com a numeração impressa: pages[47] é a 47."""

    def __init__(self, path):
        self._pages = PdfReader(str(path)).pages

    def text(self, first, last):
        return "\n".join(self._pages[p].extract_text() or "" for p in range(first, last + 1))


def flatten(text):
    return " ".join(text.split())


def sentences(text, count=1):
    parts = re.split(r'(?<=[.!?])\s+', flatten(text))
    return " ".join(parts[:count]).strip()


def section(text, start, stop_patterns):
    """Trecho entre um marcador e o primeiro dos marcadores seguintes."""
    i = text.find(start)
    if i < 0:
        return None
    rest = text[i + len(start):]
    ends = [m.start() for p in stop_patterns for m in [re.search(p, rest)] if m]
    return rest[:min(ends)] if ends else rest


def build_abilities(book):
    text = book.text(*ABILITY_CHAPTER)
    out = []
    for ability_id, name in ABILITIES:
        body = section(text, f"TESTES DE {name.upper()}", [r'\n[A-ZÀ-Ú][A-ZÀ-Ú\s]{4,}\n'])
        if not body:
            raise ExtractionError(f"habilidade {name}: seção 'TESTES DE' não encontrada")
        out.append({"id": ability_id, "name": name, "desc": sentences(body)})
    return {"abilities": out}


def build_skills(book):
    text = book.text(*ABILITY_CHAPTER)
    names = [name for _, name, _ in SKILLS]
    out = []
    for skill_id, name, ability in SKILLS:
        others = [re.escape(n) + r'\.' for n in names if n != name] + [r'Outros Testes de', r'\n•']
        body = section(text, f"\n{name}. ", others)
        if not body:
            raise ExtractionError(f"perícia {name}: parágrafo não encontrado no capítulo de habilidades")
        out.append({"id": skill_id, "name": name, "ability": ability, "desc": sentences(body)})
    return {"skills": out}



NOT_HEADERS = (SIZES | LANGUAGES
               | {name for _, name, _ in SKILLS}
               | {name for _, name in ABILITIES}
               | {r["name"] for r in RACES}
               | {r["section"].title() for r in RACES})


def not_a_header(word):
    """Palavra capitalizada que cai no início de linha por quebra de texto."""
    return word in NOT_HEADERS


def split_traits(body):
    marks = []
    listing = False
    for m in TRAIT_HEADER.finditer(body):
        title = m.group(1)
        if listing or title.isupper() or not_a_header(title):
            continue
        # Um traço só começa depois do ponto final do anterior. Palavra que caiu
        # no início da linha por quebra de texto vem após linha sem pontuação.
        # O sufixo numérico descartado é o número de página impresso no meio.
        before = re.sub(r'[\s\d]+$', '', body[:m.start()])
        if before and not before.endswith((".", "!", "?")):
            # Dois-pontos abre uma lista de opções dentro do traço corrente; os
            # itens dela seguem até o fim do bloco e não são traços novos.
            listing = before.endswith(":")
            continue
        marks.append((m.start(), m.end(), title))

    out = []
    for n, (_, end, title) in enumerate(marks):
        stop = marks[n + 1][0] if n + 1 < len(marks) else len(body)
        out.append((title, flatten(body[end:stop])))
    return out


def parse_ability_bonus(text):
    if re.search(r'Todos os seus valores de habilidade aumentam em (\d+)', text):
        amount = int(re.search(r'aumentam em (\d+)', text).group(1))
        return {a: amount for a, _ in ABILITIES}, None
    bonus = {}
    for name, amount in re.findall(r'valor de ([A-ZÀ-Ú][\wÀ-ÿ]+) aumenta em (\d+)', text):
        if name not in ABILITY_BY_NAME:
            raise ExtractionError(f"bônus racial cita habilidade desconhecida: {name!r}")
        bonus[ABILITY_BY_NAME[name]] = int(amount)
    choice = None
    m = re.search(r'(dois|dúas|duas|três) outros valores de habilidade[^.]*aumentam em (\d+)', text)
    if m:
        choice = {"count": {"dois": 2, "duas": 2, "três": 3}[m.group(1)], "amount": int(m.group(2))}
    return bonus, choice


def parse_speed(text):
    m = re.search(r'(\d+(?:,\d+)?)\s*metros', text)
    if not m:
        raise ExtractionError(f"deslocamento sem valor em metros: {text[:80]!r}")
    return m.group(1).replace(",", ".")


def parse_size(text):
    m = re.search(r'tamanho é ([A-ZÀ-Ú][\wÀ-ÿ]+)', text)
    if not m or m.group(1) not in SIZES:
        raise ExtractionError(f"tamanho fora do vocabulário: {text[:80]!r}")
    return m.group(1)


def build_entry(traits, where):
    entry = {"traits": []}
    for title, desc in traits:
        if title == "Aumento no Valor de Habilidade":
            bonus, choice = parse_ability_bonus(desc)
            entry["abilityBonus"] = bonus
            if choice:
                entry["abilityChoice"] = choice
        elif title == "Tamanho":
            entry["size"] = parse_size(desc)
            entry["sizeDesc"] = desc
        elif title == "Deslocamento":
            entry["speed"] = parse_speed(desc)
        elif title == "Idade":
            entry["age"] = desc
        elif title == "Tendência":
            entry["alignment"] = desc
        elif title == "Idiomas":
            entry["languages"] = desc
        elif title == "Sub-raça":
            continue
        else:
            entry["traits"].append({"name": title, "desc": desc})
    if "abilityBonus" not in entry:
        raise ExtractionError(f"{where}: sem Aumento no Valor de Habilidade")
    return entry


def build_races(book):
    out = []
    for race in RACES:
        text = book.text(*race["pages"])
        start = text.find(f"TRAÇOS RACIAIS DOS {race['section']}")
        if start < 0:
            raise ExtractionError(f"raça {race['name']}: seção de traços não encontrada")

        stop_at = text.find("TRAÇOS RACIAIS ALTERNATIVOS", start)
        if stop_at > 0:
            text = text[:stop_at]

        cuts = []
        for sub_id, sub_name, heading in race["subraces"]:
            at = text.find(f"\n{heading}", start)
            if at < 0:
                raise ExtractionError(f"raça {race['name']}: sub-raça {heading!r} não encontrada")
            cuts.append((at, sub_id, sub_name))
        cuts.sort()

        base_end = cuts[0][0] if cuts else len(text)
        entry = {"id": race["id"], "name": race["name"]}
        entry.update(build_entry(split_traits(text[start:base_end]), race["name"]))

        subraces = []
        for n, (at, sub_id, sub_name) in enumerate(cuts):
            stop = cuts[n + 1][0] if n + 1 < len(cuts) else len(text)
            sub = {"id": sub_id, "name": sub_name}
            sub.update(build_entry(split_traits(text[at:stop]), sub_name))
            subraces.append(sub)
        if subraces:
            entry["subraces"] = subraces
        out.append(entry)
    return {"races": out}


CATALOGS = {
    "abilities.json": build_abilities,
    "skills.json": build_skills,
    "races.json": build_races,
}

EXPECTED_COUNTS = {"abilities.json": 6, "skills.json": 18, "races.json": 9}


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
        items = next(v for v in payload.values() if isinstance(v, list))
        expected = EXPECTED_COUNTS[filename]
        if len(items) != expected:
            sys.exit(f"{filename}: {len(items)} itens, esperado {expected}")
        write(OUT / filename, payload)
        print(f"  {filename:<20} {len(items):>3} itens")


if __name__ == "__main__":
    try:
        main()
    except ExtractionError as err:
        sys.exit(f"extração abortada: {err}")
