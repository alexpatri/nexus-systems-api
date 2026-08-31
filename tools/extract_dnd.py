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

# O Word exporta o marcador de lista como este glifo da área privada.
BULLET = "\uf0b7"

NUMBER_WORDS = {"uma": 1, "duas": 2, "dois": 2, "três": 3, "quatro": 4, "cinco": 5}

CLASSES = [
    {"id": "barbarian", "name": "Bárbaro", "pages": (46, 50),
     "level1": ["Fúria", "Defesa sem Armadura"]},
    {"id": "bard", "name": "Bardo", "pages": (51, 55),
     "level1": ["Conjuração", "Inspiração de Bardo"]},
    {"id": "warlock", "name": "Bruxo", "pages": (56, 62),
     "level1": ["Patrono Transcendental", "Magia de Pacto"]},
    {"id": "cleric", "name": "Clérigo", "pages": (63, 70),
     "level1": ["Conjuração", "Domínio Divino"]},
    {"id": "druid", "name": "Druida", "pages": (71, 76),
     "level1": ["Druídico", "Conjuração"]},
    {"id": "sorcerer", "name": "Feiticeiro", "pages": (77, 82),
     "level1": ["Conjuração", "Origem de Feitiçaria"]},
    {"id": "fighter", "name": "Guerreiro", "pages": (83, 88),
     "level1": ["Estilo de Luta", "Retomar o Fôlego"]},
    {"id": "rogue", "name": "Ladino", "pages": (89, 93),
     "level1": ["Especialização", "Ataque Furtivo", "Gíria de Ladrão"]},
    {"id": "wizard", "name": "Mago", "pages": (94, 101),
     "level1": ["Conjuração", "Recuperação Arcana"]},
    {"id": "monk", "name": "Monge", "pages": (102, 107),
     "level1": ["Defesa sem Armadura", "Artes Marciais"]},
    {"id": "paladin", "name": "Paladino", "pages": (108, 114),
     "level1": ["Sentido Divino", "Cura pelas Mãos"]},
    {"id": "ranger", "name": "Patrulheiro", "pages": (115, 120),
     "level1": ["Inimigo Favorito", "Explorador Natural"]},
]

BACKGROUNDS = [
    {"id": "acolyte", "name": "Acólito", "page": 127},
    {"id": "guild-artisan", "name": "Artesão de Guilda", "page": 128},
    {"id": "entertainer", "name": "Artista", "page": 129},
    {"id": "charlatan", "name": "Charlatão", "page": 131},
    {"id": "criminal", "name": "Criminoso", "page": 132},
    {"id": "hermit", "name": "Eremita", "page": 133},
    {"id": "outlander", "name": "Forasteiro", "page": 134},
    {"id": "folk-hero", "name": "Herói do Povo", "page": 135},
    {"id": "sailor", "name": "Marinheiro", "page": 136},
    {"id": "noble", "name": "Nobre", "page": 137},
    {"id": "urchin", "name": "Órfão", "page": 138},
    {"id": "sage", "name": "Sábio", "page": 139},
    {"id": "soldier", "name": "Soldado", "page": 140},
]


SKILL_BY_NAME = {name.lower(): (skill_id, name, ability) for skill_id, name, ability in SKILLS}


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



def field(block, label):
    nxt = r'[A-ZÀ-Ú][a-zà-ú]+(?:\s+(?:de|em|com|a)\s+[A-ZÀ-Ú][a-zà-ú]+)*:'
    m = re.search(rf'{label}:\s*(.+?)(?=\s+{nxt}|$)', block)
    # O número de página impresso cai dentro do bloco e gruda no fim do campo.
    return re.sub(r'\s*\d+\s*$', '', flatten(m.group(1))) if m else None


def parse_saving(text):
    out = []
    for name in re.split(r',\s*|\s+e\s+', text):
        name = name.strip()
        if name not in ABILITY_BY_NAME:
            raise ExtractionError(f"teste de resistência desconhecido: {name!r}")
        out.append(ABILITY_BY_NAME[name])
    return out


def parse_skill_choice(text, where):
    m = re.match(r'Escolha (\w+)\s+(?:d?entre\s+(.+)|quaisquer)', text)
    if not m:
        raise ExtractionError(f"{where}: escolha de perícias não reconhecida: {text[:70]!r}")
    if m.group(1) not in NUMBER_WORDS:
        raise ExtractionError(f"{where}: quantidade desconhecida: {m.group(1)!r}")
    qtd = NUMBER_WORDS[m.group(1)]

    if m.group(2) is None:
        chosen = [(i, n, a) for i, n, a in SKILLS]
    else:
        chosen = []
        for name in re.split(r',\s*|\s+e\s+', m.group(2)):
            key = name.strip().rstrip(".").lower()
            if key not in SKILL_BY_NAME:
                raise ExtractionError(f"{where}: perícia fora do vocabulário: {name!r}")
            chosen.append(SKILL_BY_NAME[key])

    return {"qtd": qtd,
            "skills": [{"id": i, "name": n, "ability": a} for i, n, a in chosen]}


def cut_section(text, start):
    """Do cabeçalho até o próximo em caixa alta, que abre a seção seguinte."""
    rest = text[start:]
    body = rest[rest.index("\n"):] if "\n" in rest else rest
    stop = re.search(r'\n[A-ZÀ-Ú][A-ZÀ-Ú0-9\s\-]{3,40}\n', body)
    return body[:stop.start()] if stop else body


def parse_equipment(block):
    out = []
    for chunk in block.split(BULLET)[1:]:
        text = re.sub(r'\s*\d+\s*$', '', flatten(chunk))
        if not text:
            continue
        options = [o.strip() for o in re.split(r'\s*\([a-z]\)\s*', text) if o.strip()]
        if len(options) > 1:
            out.append({"choose": [re.sub(r'(,|\s+ou)$', '', o) for o in options]})
        else:
            out.append({"item": text})
    return out


def build_classes(book):
    out = []
    for klass in CLASSES:
        text = book.text(*klass["pages"])
        flat = flatten(text)

        die = re.search(r'Dado de Vida:\s*1d(\d+)', flat)
        if not die:
            raise ExtractionError(f"classe {klass['name']}: dado de vida não encontrado")

        prof_at = text.find("PROFICIÊNCIAS")
        equip_at = text.find("EQUIPAMENTO", prof_at)
        if prof_at < 0 or equip_at < 0:
            raise ExtractionError(f"classe {klass['name']}: bloco de proficiências ou equipamento ausente")
        prof = flatten(text[prof_at:equip_at])

        entry = {
            "id": klass["id"],
            "name": klass["name"],
            "hitDie": int(die.group(1)),
            "saving": parse_saving(field(prof, "Testes de Resistência")),
            "proficiencies": {
                "armor": field(prof, "Armaduras"),
                "weapons": field(prof, "Armas"),
                "tools": field(prof, "Ferramentas"),
            },
            "proficiency": parse_skill_choice(field(prof, "Perícias"), klass["name"]),
            "startingEquipment": parse_equipment(cut_section(text, equip_at)),
            "features": [],
        }

        for name in klass["level1"]:
            at = text.find(f"\n{name.upper()}")
            if at < 0:
                raise ExtractionError(f"classe {klass['name']}: característica {name!r} sem seção no texto")
            rest = text[at + 1 + len(name):]
            stop = re.search(r'\n[A-ZÀ-Ú][A-ZÀ-Ú0-9\s\-]{3,40}\n', rest)
            entry["features"].append({
                "name": name,
                "desc": flatten(rest[:stop.start()] if stop else rest[:2000]),
            })
        out.append(entry)
    return {"classes": out}



CONNECTORS = {"de", "do", "da", "dos", "das", "e", "em", "no", "na", "a", "o", "com", "para"}


def title_case(text):
    words = text.lower().split()
    return " ".join(w if n and w in CONNECTORS else w.capitalize() for n, w in enumerate(words))


def parse_skill_list(text, where):
    out = []
    for name in re.split(r',\s*|\s+e\s+', text):
        key = name.strip().rstrip(".").lower()
        if not key:
            continue
        if key not in SKILL_BY_NAME:
            raise ExtractionError(f"{where}: perícia fora do vocabulário: {name!r}")
        skill_id, skill_name, ability = SKILL_BY_NAME[key]
        out.append({"id": skill_id, "name": skill_name, "ability": ability})
    return out


def build_backgrounds(book):
    headings = {bg["name"].upper() for bg in BACKGROUNDS}
    out = []
    for bg in BACKGROUNDS:
        text = book.text(bg["page"], bg["page"] + 1)
        heading = bg["name"].upper()
        start = text.find(f"\n{heading}")
        if start < 0:
            raise ExtractionError(f"antecedente {bg['name']}: cabeçalho não encontrado")

        rest = text[start + 1:]
        ends = [rest.find(f"\n{h}") for h in headings if h != heading]
        ends = [e for e in ends if e > 0]
        body = rest[:min(ends)] if ends else rest

        feature_at = body.find("CARACTERÍSTICA:")
        if feature_at < 0:
            raise ExtractionError(f"antecedente {bg['name']}: sem bloco CARACTERÍSTICA")
        fields_at = body.find("Proficiência em Perícias")
        if fields_at < 0:
            raise ExtractionError(f"antecedente {bg['name']}: bloco de campos não encontrado")
        region = body[fields_at:feature_at]
        table = re.search(r'\n[A-ZÀ-Ú][A-ZÀ-Ú0-9\s\-]{3,40}\n', region)
        head = flatten(region[:table.start()] if table else region)
        feature = body[feature_at:]

        skills = field(head, "Proficiência em Perícias")
        if not skills:
            raise ExtractionError(f"antecedente {bg['name']}: sem proficiência em perícias")

        title_end = feature.index("\n")
        entry = {
            "id": bg["id"],
            "name": bg["name"],
            "skills": parse_skill_list(skills, bg["name"]),
            "tools": field(head, "Proficiência em Ferramentas"),
            "languages": field(head, "Idiomas"),
            "equipment": field(head, "Equipamento"),
            "feature": {
                "name": title_case(feature[len("CARACTERÍSTICA:"):title_end]),
                "desc": flatten(cut_section(feature, 0)),
            },
        }
        out.append(entry)
    return {"backgrounds": out}


CATALOGS = {
    "abilities.json": build_abilities,
    "skills.json": build_skills,
    "races.json": build_races,
    "classes.json": build_classes,
    "backgrounds.json": build_backgrounds,
}

EXPECTED_COUNTS = {"abilities.json": 6, "skills.json": 18, "races.json": 9, "classes.json": 12, "backgrounds.json": 13}


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
