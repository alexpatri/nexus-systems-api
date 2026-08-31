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


CATALOGS = {
    "abilities.json": build_abilities,
    "skills.json": build_skills,
}

EXPECTED_COUNTS = {"abilities.json": 6, "skills.json": 18}


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
