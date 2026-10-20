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
import unicodedata

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

GROUPS = [
    ("acting", "Atuação"), ("athletics", "Atletismo"), ("biotech", "Biotecnologia"),
    ("close-combat", "Combate Corpo a Corpo"), ("conjuring", "Convocação"),
    ("cracking", "Quebra de Dados"), ("electronics", "Eletrônica"), ("enchanting", "Encantação"),
    ("engineering", "Engenharia"), ("firearms", "Armas de Fogo"), ("influence", "Influência"),
    ("outdoors", "Ar Livre"), ("sorcery", "Feitiçaria"), ("stealth", "Furtividade"),
    ("tasking", "Tarefa"),
]

# (id, nome, atributo, categoria, grupo, exige especificar a arma/veículo)
SKILLS = [
    ("exotic-ranged-weapon", "Arma a Distância Exótica", "agi", "combat", None, True),
    ("exotic-melee-weapon", "Arma Corpo a Corpo Exótica", "agi", "combat", None, True),
    ("throwing-weapons", "Armas de Arremesso", "agi", "combat", None, False),
    ("longarms", "Armas de Cano Longo", "agi", "combat", "firearms", False),
    ("heavy-weapons", "Armas Pesadas", "agi", "combat", None, False),
    ("archery", "Arquearia", "agi", "combat", None, False),
    ("automatics", "Automáticas", "agi", "combat", "firearms", False),
    ("clubs", "Bastões", "agi", "combat", "close-combat", False),
    ("unarmed-combat", "Combate Desarmado", "agi", "combat", "close-combat", False),
    ("blades", "Lâminas", "agi", "combat", "close-combat", False),
    ("pistols", "Pistolas", "agi", "combat", "firearms", False),
    ("escape-artist", "Arte da Fuga", "agi", "physical", None, False),
    ("running", "Corrida", "str", "physical", "athletics", False),
    ("disguise", "Disfarce", "int", "physical", "stealth", False),
    ("palming", "Empalmar", "agi", "physical", "stealth", False),
    ("sneaking", "Esgueirar", "agi", "physical", "stealth", False),
    ("gymnastics", "Ginástica", "agi", "physical", "athletics", False),
    ("diving", "Mergulho", "bod", "physical", None, False),
    ("swimming", "Natação", "str", "physical", "athletics", False),
    ("perception", "Percepção", "int", "physical", None, False),
    ("free-fall", "Queda Livre", "bod", "physical", None, False),
    ("tracking", "Rastrear", "int", "physical", "outdoors", False),
    ("survival", "Sobrevivência", "wil", "physical", "outdoors", False),
    ("etiquette", "Etiqueta", "cha", "social", "influence", False),
    ("instruction", "Instrução", "cha", "social", None, False),
    ("intimidation", "Intimidação", "cha", "social", None, False),
    ("leadership", "Liderança", "cha", "social", "influence", False),
    ("negotiation", "Negociação", "cha", "social", "influence", False),
    ("performance", "Performance", "cha", "social", "acting", False),
    ("impersonation", "Personificação", "cha", "social", "acting", False),
    ("con", "Trapaça", "cha", "social", "acting", False),
    ("alchemy", "Alquimia", "mag", "magical", "enchanting", False),
    ("arcana", "Arcana", "log", "magical", None, False),
    ("artificing", "Artificiaria", "mag", "magical", "enchanting", False),
    ("banishing", "Banimento", "mag", "magical", "conjuring", False),
    ("astral-combat", "Combate Astral", "wil", "magical", None, False),
    ("spellcasting", "Conjuração", "mag", "magical", "sorcery", False),
    ("ritual-spellcasting", "Conjuração Ritual", "mag", "magical", "sorcery", False),
    ("counterspelling", "Contramágica", "mag", "magical", "sorcery", False),
    ("disenchanting", "Desencantação", "mag", "magical", "enchanting", False),
    ("summoning", "Invocação", "mag", "magical", "conjuring", False),
    ("assensing", "Sentido Astral", "int", "magical", None, False),
    ("binding", "Vinculação", "mag", "magical", "conjuring", False),
    ("compiling", "Compilar", "res", "resonance", "tasking", False),
    ("decompiling", "Descompilar", "res", "resonance", "tasking", False),
    ("registering", "Registrar", "res", "resonance", "tasking", False),
    ("animal-handling", "Adestrar Animais", "cha", "technical", None, False),
    ("armorer", "Armeiro", "log", "technical", None, False),
    ("artisan", "Artesão", "int", "technical", None, False),
    ("biotechnology", "Bioengenharia", "log", "technical", "biotech", False),
    ("locksmith", "Chaveiro", "agi", "technical", None, False),
    ("cybercombat", "Cibercombate", "log", "technical", "cracking", False),
    ("cybertechnology", "Cibertecnologia", "log", "technical", "biotech", False),
    ("computer", "Computador", "log", "technical", "electronics", False),
    ("demolitions", "Demolições", "log", "technical", None, False),
    ("forgery", "Falsificação", "log", "technical", None, False),
    ("electronic-warfare", "Guerra Eletrônica", "log", "technical", "cracking", False),
    ("hacking", "Hackear", "log", "technical", "cracking", False),
    ("hardware", "Hardware", "log", "technical", "electronics", False),
    ("aeronautics-mechanic", "Mecânica Aeronáutica", "log", "technical", "engineering", False),
    ("automotive-mechanic", "Mecânica Automotiva", "log", "technical", "engineering", False),
    ("industrial-mechanic", "Mecânica Industrial", "log", "technical", "engineering", False),
    ("nautical-mechanic", "Mecânica Náutica", "log", "technical", "engineering", False),
    ("medicine", "Medicina", "log", "technical", "biotech", False),
    ("navigation", "Navegação", "int", "technical", "outdoors", False),
    ("first-aid", "Primeiros Socorros", "log", "technical", "biotech", False),
    ("chemistry", "Química", "log", "technical", None, False),
    ("software", "Software", "log", "technical", "electronics", False),
    ("gunnery", "Artilharia", "agi", "vehicle", None, False),
    ("pilot-aircraft", "Pilotar Aeronaves", "rea", "vehicle", None, False),
    ("pilot-walker", "Pilotar Andarilhos", "rea", "vehicle", None, False),
    ("pilot-watercraft", "Pilotar Embarcações", "rea", "vehicle", None, False),
    ("pilot-aerospace", "Pilotar Espaçonaves", "rea", "vehicle", None, False),
    ("pilot-exotic-vehicle", "Pilotar Veículos Exóticos", "rea", "vehicle", None, True),
    ("pilot-ground-craft", "Pilotar Veículos Terrestres", "rea", "vehicle", None, False),
]

# A perícia só aparece nas listas (p. 90 e 151): o capítulo de perícias não tem
# bloco para ela. Teste-padrão e especializações seguem Arma a Distância Exótica.
NO_BLOCK = {"exotic-melee-weapon"}

# Grafias da lista da p. 151 que divergem do nome canônico.
P151_NAMES = {"exotic-melee-weapon": "Armas Corpo a Corpo Exótica"}

KNOWLEDGE_CATEGORIES = [
    ("academic", "Acadêmica", "log"),
    ("interests", "Interesses", "int"),
    ("professional", "Profissional", "log"),
    ("street", "Ruas", "int"),
]


def notoriety(n):
    return {"target": "reputation.notoriety", "add": n}


def fixed(karma):
    return {"karma": karma}


def per_level(karma, max_level):
    return {"karma": {"perLevel": karma}, "levels": {"max": max_level}}


def options(*opts):
    return {"karma": {"options": [dict(zip(("id", "name", "karma"), o[:3]), **(o[3] if len(o) > 3 else {}))
                                  for o in opts]}}


def factors(*facs):
    return {"karma": {"sum": [{"id": fid, "name": name,
                               "options": [dict(zip(("id", "name", "karma"), o)) for o in opts]}
                              for fid, name, opts in facs]}}


# (id, nome, grafia do livro quando difere do nome, custo, modificadores)
POSITIVE_QUALITIES = [
    ("spirit-affinity", "Afinidade Espiritual", None, fixed(7), []),
    ("high-pain-tolerance", "Alto Limiar de Dor", None, per_level(7, 3),
     [{"target": "wound.ignoredBoxes", "add": ref("rating")}]),
    ("ambidextrous", "Ambidestria", None, fixed(4), []),
    ("human-looking", "Aparência Humana", None, fixed(6), []),
    ("aptitude", "Aptidão", None, fixed(14),
     [{"target": "skill.max", "of": {"choose": "skill"}, "add": 1}]),
    ("natural-athlete", "Atleta Natural", None, fixed(7), []),
    ("exceptional-attribute", "Atributo Excepcional", None, fixed(14),
     [{"target": "attr.max", "of": {"choose": "attribute", "except": ["ess", "edg"]}, "add": 1}]),
    ("bilingual", "Bilíngue", None, fixed(5), [{"target": "language.native", "add": 1}]),
    ("blandness", "Cara Genérica", None, fixed(8), [notoriety(-1)]),
    ("astral-chameleon", "Camaleão Astral", None, fixed(10), []),
    ("focused-concentration", "Concentração Focada", None, per_level(4, 6), []),
    ("guts", "Coragem", None, fixed(10), []),
    ("quick-healer", "Curandeiro Rápido", None, fixed(3), []),
    ("will-to-live", "Desejo de Viver", None, per_level(3, 3),
     [{"target": "monitor.overflow", "add": ref("rating")}]),
    ("natural-hardening", "Endurecimento Natural", None, fixed(10),
     [{"target": "matrix.biofeedbackFilter", "add": 1}]),
    ("mentor-spirit", "Espírito Mentor", None, fixed(5), []),
    ("catlike", "Felino", None, fixed(7), []),
    ("jury-rigger", "Gambiarra", None, fixed(10), []),
    ("natural-immunity", "Imunidade Natural", None,
     options(("natural", "Doença ou toxina natural", 4), ("synthetic", "Doença ou toxina sintética", 10)), []),
    ("indomitable", "Indomável", None, per_level(8, 3),
     [{"target": "limit", "of": {"choose": "limit"}, "add": 1, "times": ref("rating")}]),
    ("photographic-memory", "Memória Fotográfica", None, fixed(6), []),
    ("analytical-mind", "Mente Analítica", None, fixed(5), []),
    ("gearhead", "Piloto Nato", None, fixed(11), []),
    ("first-impression", "Primeira Impressão", None, fixed(11), [notoriety(-1)]),
    ("codeslinger", "Programador Rápido", None, fixed(10), []),
    # O livro grafa "Resistência à Patogênicos" (crase indevida).
    ("resistance-to-pathogens-toxins", "Resistência a Patogênicos/Toxinas",
     "Resistência à Patogênicos/Toxinas",
     options(("one", "Patogênicos ou toxinas", 4), ("both", "Patogênicos e toxinas", 8)), []),
    ("magic-resistance", "Resistência Mágica", None, per_level(6, 4), []),
    ("lucky", "Sortudo", None, fixed(12), [{"target": "attr.max", "of": "edg", "add": 1}, notoriety(-1)]),
    ("home-ground", "Terreno Familiar", None, fixed(10), []),
    ("double-jointed", "Ultraflexibilidade", None, fixed(6), []),
    ("toughness", "Vitalidade", None, fixed(9), []),
]

NEGATIVE_QUALITIES = [
    ("allergy", "Alergia", None, factors(
        ("prevalence", "Predominância", [("uncommon", "Incomum", 2), ("common", "Comum", 7)]),
        ("severity", "Gravidade", [("mild", "Leve", 3), ("moderate", "Moderada", 8),
                                   ("severe", "Grave", 13), ("extreme", "Extrema", 18)])), []),
    ("scorched", "Arrasado", None, fixed(10), [notoriety(1)]),
    ("bad-luck", "Azar", None, fixed(10), [notoriety(1)]),
    ("low-pain-tolerance", "Baixo Limiar de Dor", None, fixed(9),
     [{"target": "wound.boxesPerPenalty", "set": 2}]),
    ("codeblock", "Bloqueio de Código", None, fixed(10), []),
    ("code-of-honor", "Código de Honra", None, fixed(15), []),
    ("dependents", "Dependentes", None, options(
        ("nuisance", "Irritação ocasional", 3, {"modifiers": [{"target": "lifestyle.cost", "mul": 1.1}]}),
        ("inconvenience", "Inconveniência regular", 6, {"modifiers": [{"target": "lifestyle.cost", "mul": 1.2}]}),
        ("close", "Membro próximo que mora junto", 9,
         {"modifiers": [{"target": "lifestyle.cost", "mul": 1.3}]})),
     [{"target": "progression.trainingTime", "mul": 1.5}]),
    ("elf-poser", "Elfo Poser", None, fixed(6), [notoriety(1)]),
    ("distinctive-style", "Estilo Distinto", None, fixed(5), []),
    ("astral-beacon", "Farol Astral", None, fixed(10), []),
    ("gremlins", "Gremlins", None, per_level(4, 4), [notoriety(1)]),
    ("incompetent", "Incompetente", None, fixed(5), [notoriety(1)]),
    ("uneducated", "Inculto", None, fixed(8), [notoriety(1)]),
    ("insomnia", "Insônia", None, options(("mild", "Leve", 10), ("severe", "Grave", 15)), []),
    ("bad-rep", "Má Reputação", None, fixed(7), [notoriety(3)]),
    ("unsteady-hands", "Mãos Instáveis", None, fixed(7), []),
    ("ork-poser", "Ork Poser", None, fixed(6), [notoriety(1)]),
    ("combat-paralysis", "Paralisia de Combate", None, fixed(12), [notoriety(1)]),
    ("loss-of-confidence", "Perda de Confiança", None, fixed(10), []),
    ("prejudiced", "Preconceituoso", None, factors(
        ("prevalence", "Predominância do grupo alvo", [("specific", "Grupo alvo específico", 3),
                                                      ("common", "Grupo alvo comum", 5)]),
        ("degree", "Grau", [("biased", "Inclinado", 0), ("outspoken", "Aberto", 2),
                            ("radical", "Radical", 5)])), []),
    ("uncouth", "Rude", None, fixed(14), [notoriety(1)]),
    ("spirit-bane", "Ruína Espiritual", None, fixed(7), [notoriety(1)]),
    ("sinner", "Sinado (Camada)", None, options(
        ("national", "SIN Nacional", 5),
        ("criminal", "SIN Criminoso", 10, {"modifiers": [notoriety(1)]}),
        ("corporate-limited", "SIN Corporativo Limitado", 15),
        ("corporate-born", "Nato Corporativo", 25)), []),
    ("weak-immune-system", "Sistema Imunológico Fraco", None, fixed(10), [notoriety(1)]),
    ("sensitive-system", "Sistema Sensível", None, fixed(12),
     [{"target": "essence.cyberwareLoss", "mul": 2}]),
    ("social-stress", "Tensão Social", None, fixed(8), []),
    ("simsense-vertigo", "Vertigem de Sensorama", None, fixed(5), []),
    ("addiction", "Vício", None, options(
        ("mild", "Leve", 4), ("moderate", "Moderado", 9), ("severe", "Severo", 20),
        ("burnout", "Esgotamento", 25), ), [notoriety(1)]),
]

# Notoriedade, p. 368. Má Reputação não está na lista, mas a própria qualidade
# (p. 82) diz que o personagem começa com 3 pontos.
NOTORIETY_P368 = {
    "positive": ["Cara Genérica", "Primeira Impressão", "Sortudo"],
    "negative": ["Arrasado", "Azar", "Elfo Poser", "Gremlins", "Incompetente", "Inculto", "Ork Poser",
                 "Paralisia de Combate", "Rude", "Ruína Espiritual", "SINado", "Sistema Imunológico Fraco",
                 "Vício"],
}

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


def fold(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def is_heading(line):
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


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


# Box "o que os níveis significam", que corta o bloco de Arquearia.
SKILL_SIDEBARS = {131: ("Esta é uma lista do que os Níveis", "qualidade Aptidão (p. 72).")}


def skill_lines(book):
    lines = []
    for p in range(130, 151):
        page = book.page(p).split("\n")
        if p in SKILL_SIDEBARS:
            first, last = SKILL_SIDEBARS[p]
            i = next((k for k, line in enumerate(page) if line.startswith(first)), None)
            j = next((k for k, line in enumerate(page) if line.endswith(last)), None)
            if i is None or j is None:
                raise ExtractionError(f"box lateral da p. {p} não encontrado: {first!r}")
            page = page[:i] + page[j + 1:]
        lines += [(p, line) for line in page]
    return lines


def build_skills(book):
    numbered = skill_lines(book)
    lines = [line for _, line in numbered]
    p151 = book.page(151)
    p153 = book.page(153)
    p90 = book.prose(book.page(90))
    out = []
    for sid, name, attribute, category, group, specific in SKILLS:
        entry = {"id": sid, "name": name, "attribute": attribute, "category": category, "group": group,
                 "specific": specific, "restricted": attribute in ("mag", "res")}
        check_p151(p151, sid, name, attribute)
        if sid in NO_BLOCK:
            require(p90, f"{name} (Específica)", f"perícia {name}")
            entry.update({"default": False, "specializations": [], "desc": None, "page": 90})
            out.append(entry)
            continue

        heading = re.compile(rf'^{re.escape(name.upper())}(?: \((\w+)\))?\s*$')
        starts = [i for i, line in enumerate(lines) if heading.match(line.strip())]
        if len(starts) != 1:
            raise ExtractionError(f"perícia {name}: {len(starts)} cabeçalhos encontrados no capítulo")
        start = starts[0]
        header_attr = heading.match(lines[start].strip()).group(1)

        i = start + 1
        # "(ESPECÍFICA)" ou o atributo podem cair na linha de baixo do nome.
        m = re.match(r'^\((\w+)\)$', lines[i].strip())
        if m:
            if m.group(1) not in ("ESPECÍFICA", "ESPECÍFICO"):
                header_attr = m.group(1)
            i += 1
        if header_attr and fold(header_attr) != fold(ATTRIBUTE_NAMES[attribute]):
            raise ExtractionError(f"perícia {name}: cabeçalho diz {header_attr}, vocabulário diz {attribute}")
        desc = []
        while not lines[i].startswith("Teste-Padrão") and not is_heading(lines[i]):
            desc.append(lines[i])
            i += 1
        while not lines[i].startswith("Teste-Padrão"):
            i += 1
        default = lines[i].split(":", 1)[1].strip()
        if not lines[i + 1].startswith("Grupo de Perícias:") or not lines[i + 2].startswith("Especializações:"):
            raise ExtractionError(f"perícia {name}: bloco Teste-Padrão/Grupo/Especializações fora do formato")
        block_group = lines[i + 1].split(":", 1)[1].strip().rstrip(".")
        specs = [lines[i + 2].split(":", 1)[1]]
        j = i + 3
        while j < len(lines) and not is_heading(lines[j]) and not re.match(r'(Teste-Padrão|Grupo de)', lines[j]) \
                and not specs[-1].rstrip().endswith(".") and len(specs) < 4:
            specs.append(lines[j])
            j += 1

        expected_group = dict(GROUPS).get(group, "Nenhum")
        if block_group not in ("Nenhum", "Não") or group:
            if block_group != expected_group:
                raise ExtractionError(f"perícia {name}: grupo no livro {block_group!r}, vocabulário {group!r}")
        if default not in ("Sim", "Não"):
            raise ExtractionError(f"perícia {name}: teste-padrão ilegível {default!r}")
        spec_text = book.prose("\n".join(specs))
        entry.update({
            "default": default == "Sim",
            "specializations": [] if spec_text in ("Nenhum", "N/D") else split_list(spec_text),
            "desc": book.prose("\n".join(desc)),
            "page": numbered[start][0],
        })
        out.append(entry)

    groups = []
    for gid, gname in GROUPS:
        members = [s["id"] for s in out if s["group"] == gid]
        names = [s["name"] for s in out if s["group"] == gid]
        if gid != "influence":
            body = section(p153, f"\n{gname.upper()}\n", [r'^[A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{4,}$'])
            if body is None:
                raise ExtractionError(f"grupo {gname}: lista da p. 153 não encontrada")
            listed = {line.strip() for line in body.split("\n") if line.strip()}
            if listed != set(names):
                raise ExtractionError(f"grupo {gname}: p. 153 lista {sorted(listed)}, vocabulário {sorted(names)}")
        else:
            # A p. 153 omite Influência; a lista da p. 90 é a única fonte.
            require(book.page(90), "INFLUÊNCIA", "grupo Influência")
        groups.append({"id": gid, "name": gname, "skills": members})

    knowledge = build_knowledge(book)
    return {"skills": out, "groups": groups, **knowledge}


def check_p151(p151, sid, name, attribute):
    heading = fold(ATTRIBUTE_NAMES[attribute]).upper()
    body = section(fold(p151).upper(), f"\n{heading}\n",
                   [rf'^{fold(n).upper()}$' for _, n, *_ in ATTRIBUTES if fold(n).upper() != heading]
                   + [r'^LISTA DE PERICIAS ATIVAS, CONT', r'^OBS\.'])
    listed = P151_NAMES.get(sid, name)
    if body is None or fold(listed).upper() not in body:
        raise ExtractionError(f"perícia {name}: não aparece sob {ATTRIBUTE_NAMES[attribute]} na p. 151")


def build_knowledge(book):
    p88 = book.page(88)
    p89 = book.prose(book.page(89))
    categories = []
    for cid, name, attribute in KNOWLEDGE_CATEGORIES:
        m = re.search(rf'{name} +{ATTRIBUTE_NAMES[attribute]} (.+?)(?= (?:Acadêmica|Interesses|Profissional|Ruas) '
                      rf'(?:Lógica|Intuição)|$)', p89)
        if not m:
            raise ExtractionError(f"conhecimento {name}: linha da tabela de categorias não encontrada")
        categories.append({"id": cid, "name": name, "attribute": attribute, "examples": split_list(m.group(1))})

    def bullets(title, stop):
        body = section(p88, title, [stop])
        if body is None:
            raise ExtractionError(f"lista {title!r} não encontrada na p. 88")
        items = [book.prose(b) for b in re.split(r'^•\s*', body, flags=re.M) if b.strip()]
        return items

    suggestions = bullets("PERÍCIAS DE CONHECIMENTO COMUNS EM 2075", r'^IDIOMAS COMUNS')
    languages = bullets("IDIOMAS COMUNS EM 2075", r'\Z')

    lang = book.text(150, 150)
    m = re.search(r'IDIOMA \(INTUIÇÃO\)\n(.+?)\nTeste-Padrão:\s*Sim\nGrupo de Perícias:\s*Nenhum\n'
                  r'Especializações:\s*(.+?)\n(?=[A-ZÁÉÍÓÚ ]{4,}\n)', lang, re.S)
    if not m:
        raise ExtractionError("perícia Idioma: bloco da p. 150 não encontrado")
    require(p89, "(nível de Intuição + nível de Lógica) x 2", "pontos de conhecimento")
    return {
        "knowledge": {"categories": categories, "suggestions": suggestions, "page": 89},
        "languages": {"attribute": "int", "native": {"free": 1, "rating": "N"},
                      "default": True, "specializations": split_list(book.prose(m.group(2))),
                      "desc": book.prose(m.group(1)), "suggestions": languages, "page": 150},
    }


QUALITY_COST = re.compile(r'^(CUSTO|BÔNUS):\s*(.+?)\s*$')

# Boxes laterais que cortam o texto das qualidades: (primeira linha, última
# linha ou None para ir até o fim da página).
QUALITY_SIDEBARS = {
    73: ("QUALIDADES POSITIVAS", None),  # tabela-resumo, conferida à parte
    78: ("TABELA DE EFEITOS COLATERAIS", None),
    83: ("TABELA DE PRECONCEITUOSO", "Radical (ex.: supremacia racial) 5 Carma"),
    85: ("VÍCIOS COMUNS", None),
    86: ("EXEMPLO", None),  # página inteira de exemplo
}

SCORCHED_EFFECTS = ["Perda de Memória (curto prazo)", "Perda de Memória (longo prazo)", "Apagão",
                    "Enxaquecas", "Paranoia/Ansiedade"]


def expected_numbers(spec):
    karma = spec["karma"]
    if isinstance(karma, int):
        return [karma]
    if "perLevel" in karma:
        return [karma["perLevel"], spec["levels"]["max"]]
    if "options" in karma:
        return sorted(o["karma"] for o in karma["options"])
    totals = [0]
    for factor in karma["sum"]:
        totals = [t + o["karma"] for t in totals for o in factor["options"]]
    return [min(totals), max(totals)]


def quality_flow(book):
    """Linhas das p. 71–87 sem os boxes laterais, que voltam à parte."""
    flow, boxes = [], {}
    for p in range(71, 88):
        lines = book.page(p).split("\n")
        if p in QUALITY_SIDEBARS:
            first, last = QUALITY_SIDEBARS[p]
            i = next((k for k, line in enumerate(lines) if line.strip().startswith(first)), None)
            j = len(lines) - 1 if last is None else next(
                (k for k, line in enumerate(lines) if line.strip().startswith(last)), None)
            if i is None or j is None:
                raise ExtractionError(f"box lateral da p. {p} não encontrado: {first!r}")
            boxes[p] = "\n".join(lines[i:j + 1])
            lines = lines[:i] + lines[j + 1:]
        flow += [(p, line) for line in lines]
    return flow, boxes


def quality_blocks(flow):
    """{cabeçalho: (linha de custo, página, linhas do corpo)}."""
    costs = [k for k, (_, line) in enumerate(flow) if QUALITY_COST.match(line)]
    heads = []
    for k in costs:
        n = 2 if flow[k - 2][1].endswith("/") else 1
        heads.append((k - n, " ".join(flow[i][1].strip() for i in range(k - n, k)).replace("/ ", "/")))
    blocks = {}
    for n, k in enumerate(costs):
        end = heads[n + 1][0] if n + 1 < len(costs) else len(flow)
        body = [line for _, line in flow[k + 1:end]]
        while body and is_heading(body[-1]):  # "QUALIDADES NEGATIVAS" no fim da última positiva
            body.pop()
        blocks[fold(heads[n][1]).upper()] = (flow[k][1], flow[heads[n][0]][0], body)
    return blocks


def table_rows(text, labels):
    """Linhas "Rótulo valor descrição" de uma tabela achatada."""
    alternatives = "|".join(re.escape(label) for label in labels)
    rows = {}
    for m in re.finditer(rf'(?:^| )({alternatives}) (\d+)(?: Carma)? (.+?)(?= (?:{alternatives}) \d+ |$)', text):
        rows[m.group(1)] = m.group(3).strip()
    missing = [label for label in labels if label not in rows]
    if missing:
        raise ExtractionError(f"tabela: linhas não encontradas {missing}")
    return rows


def enrich_quality(book, entry, boxes):
    """Devolve ao catálogo o que estava nos boxes laterais."""
    qid = entry["id"]
    if qid == "allergy":
        rows = table_rows(book.prose(section(boxes[78], "TABELA DE ALERGIA", [r'\Z'])),
                          ["Incomum", "Comum", "Leve", "Moderada", "Grave", "Extrema"])
        for factor in entry["karma"]["sum"]:
            for o in factor["options"]:
                o["desc"] = rows[o["name"]]
    elif qid == "prejudiced":
        text = book.prose(boxes[83])
        for factor in entry["karma"]["sum"]:
            for o in factor["options"]:
                m = re.search(rf'{re.escape(o["name"])} \((ex\.: .+?)\) {o["karma"]} Carma', text)
                if not m:
                    raise ExtractionError(f"Preconceituoso: linha {o['name']!r} da tabela não encontrada")
                o["desc"] = m.group(1)
    elif qid == "scorched":
        text = book.prose(section(boxes[78], "EFEITO REGRAS DE JOGO", [r'TABELA DE ALERGIA']))
        # Um efeito cita o anterior pelo nome, então os rótulos são buscados em
        # sequência, cada um depois do início do anterior.
        starts, at = [], 0
        for n in SCORCHED_EFFECTS:
            at = text.find(n + " ", at)
            if at < 0:
                raise ExtractionError(f"Arrasado: efeito {n!r} não encontrado na tabela")
            starts.append(at)
            at += len(n)
        ends = starts[1:] + [len(text)]
        entry["sideEffects"] = [{"name": n, "desc": text[s + len(n):e].strip()}
                                for n, s, e in zip(SCORCHED_EFFECTS, starts, ends)]
    elif qid == "addiction":
        entry["examples"] = [book.prose(b) for b in re.split(r'^•\s*', boxes[85], flags=re.M)[1:]]


def build_qualities(book):
    flow, boxes = quality_flow(book)
    blocks = quality_blocks(flow)
    summary = book.prose(boxes[73])
    out = []
    for kind, vocab in (("positive", POSITIVE_QUALITIES), ("negative", NEGATIVE_QUALITIES)):
        for qid, name, book_name, cost, modifiers in vocab:
            printed = book_name or name
            key = fold(printed).upper()
            if key not in blocks:
                raise ExtractionError(f"qualidade {name}: cabeçalho não encontrado nas p. 71–87")
            cost_line, page, body = blocks.pop(key)

            label, amount = QUALITY_COST.match(cost_line).groups()
            if label != ("CUSTO" if kind == "positive" else "BÔNUS"):
                raise ExtractionError(f"qualidade {name}: {label} incompatível com qualidade {kind}")
            numbers = [int(n) for n in re.findall(r'\d+', amount)]
            expected = expected_numbers(cost)
            # Opções às vezes vêm como faixa ("5 A 25") em vez de lista.
            if numbers not in (expected, [expected[0], expected[-1]]):
                raise ExtractionError(f"qualidade {name}: custo no livro {cost_line!r}, vocabulário {cost['karma']}")
            # A tabela às vezes cita a página seguinte quando o cabeçalho fica no
            # pé da página; o catálogo registra onde a entrada começa.
            if not re.search(re.escape(printed) + rf' [^A-ZÁÉÍÓÚ]{{0,30}}?\b({page}|{page + 1})\b', summary):
                raise ExtractionError(f"qualidade {name}: p. 73 não lista {printed!r} na p. {page}")

            desc = book.prose("\n".join(body))
            for o in cost["karma"].get("options", []) if isinstance(cost["karma"], dict) else []:
                require(desc, f"{o['karma']} Carma", f"qualidade {name}, opção {o['name']}")

            entry = json.loads(json.dumps({"id": qid, "name": name, "kind": kind, **cost}))
            if modifiers:
                entry["modifiers"] = modifiers
            enrich_quality(book, entry, boxes)
            entry.update({"desc": desc, "page": page})
            out.append(entry)
    if blocks:
        raise ExtractionError(f"qualidades no livro fora do vocabulário: {sorted(blocks)}")

    check_notoriety(book, out)
    return {"qualities": out}


def check_notoriety(book, qualities):
    text = book.prose(book.page(368))
    for kind, names in NOTORIETY_P368.items():
        label = "Qualidades Positivas:" if kind == "positive" else "Qualidades Negativas:"
        require(text, label, "notoriedade (p. 368)")
        listed = section(text, label, [r'Qualidades Negativas:', r'Durante o jogo'])
        for name in names:
            require(listed, name, "notoriedade (p. 368)")
    by_name = {fold(q["name"]): q for q in qualities}
    marked = set()
    for q in qualities:
        mods = q.get("modifiers", []) + [m for o in (q["karma"].get("options", []) if isinstance(q["karma"], dict)
                                                     else []) for m in o.get("modifiers", [])]
        if any(m.get("target") == "reputation.notoriety" for m in mods):
            marked.add(q["id"])
    listed = {by_name[fold(n)]["id"] if fold(n) in by_name else "sinner"
              for names in NOTORIETY_P368.values() for n in names}
    if marked != listed | {"bad-rep"}:
        raise ExtractionError(f"notoriedade diverge da p. 368: {sorted(marked ^ (listed | {'bad-rep'}))}")


CATALOGS = {
    "attributes.json": build_attributes,
    "metatypes.json": build_metatypes,
    "priorities.json": build_priorities,
    "awakening.json": build_awakening,
    "skills.json": build_skills,
    "qualities.json": build_qualities,
}

EXPECTED_COUNTS = {
    "attributes.json": {"attributes": 12},
    "metatypes.json": {"metatypes": 5},
    "priorities.json": {"rows": 5},
    "awakening.json": {"awakenings": 5},
    "skills.json": {"skills": 75, "groups": 15},
    "qualities.json": {"qualities": 59},
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
