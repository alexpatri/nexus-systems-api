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
import math
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


OPS = {
    "add": lambda xs: sum(xs),
    "sub": lambda xs: xs[0] - sum(xs[1:]),
    "mul": lambda xs: math.prod(xs),
    "div": lambda xs: xs[0] / xs[1],
    "ceil": lambda xs: math.ceil(xs[0]),
    "floor": lambda xs: math.floor(xs[0]),
    "min": min,
    "max": max,
}


def evaluate(expr, env):
    if isinstance(expr, (int, float)):
        return expr
    if "ref" in expr:
        return env[expr["ref"]]
    return OPS[expr["op"]]([evaluate(a, env) for a in expr["of"]])


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

LIFESTYLES = [
    ("street", "Ruas", "RUAS", "Rua"),
    ("squatter", "Muquifo", "MUQUIFO", "Muquifo"),
    ("low", "Baixo", "BAIXO", "Baixo"),
    ("middle", "Médio", "MÉDIO", "Médio"),
    ("high", "Alto", "ALTO", "Alto"),
    ("luxury", "Luxuoso", "LUXUOSO", "Luxuoso"),
]

LIFESTYLE_OPTIONS = [
    ("special-work-area", "Área de Trabalho Especializado", "ÁREA DE TRABALHO ESPECIALIZADO",
     {"add": 1000}, "+1.000 neoienes por mês"),
    ("extra-secure", "Extra Seguro", "EXTRA SEGURO", {"percent": 20}, "+20 por cento do estilo de vida"),
    ("obscure", "Obscuro/Difícil de Encontrar", "OBSCURO/DIFÍCIL DE ENCONTRAR",
     {"percent": 10}, "+10 por cento do estilo de vida"),
    ("cramped", "Apertado", "APERTADO", {"percent": -10}, "–10 por cento do estilo de vida"),
    ("dangerous-area", "Área Perigosa", "ÁREA PERIGOSA", {"percent": -20}, "–20 por cento do estilo de vida"),
]

IDENTITIES = [
    ("fake-sin", "SIN Falso", "SIN Falso (Nível 1-6) (Nível x 3)P Nível x 2.500¥", 2500),
    ("fake-license", "Licença Falsa", "Licença falsa (Nível 1-6) (Nível x 3)P Nível x 200¥", 200),
]


SPIRIT_TYPES = [("air", "Ar"), ("beasts", "Feras"), ("earth", "Terra"), ("fire", "Fogo"), ("man", "Homem"),
                ("water", "Água")]

SPELL_CATEGORIES = [
    ("combat", "Combate"),
    ("detection", "Detecção"),
    ("health", "Saúde"),
    ("illusion", "Ilusão"),
    ("manipulation", "Manipulação"),
]

# (id, nome, box com os espíritos e o dreno, título da seção, seguidores, dreno)
TRADITIONS = [
    ("hermetic", "Hermética", "TRADIÇÃO HERMÉTICA", "O MAGO HERMÉTICO", "Magos", ("log", "wil")),
    ("shamanic", "Xamânica", "TRADIÇÃO XAMÂNICA", "O XAMÃ", "Xamãs", ("cha", "wil")),
]

# Palavras-chave como aparecem no cabeçalho dos feitiços.
SPELL_KEYWORDS = {
    "DIRETO": ("direct", "Direto"),
    "INDIRETO": ("indirect", "Indireto"),
    "ELEMENTAL": ("elemental", "Elemental"),
    "ATIVO": ("active", "Ativo"),
    "PASSIVO": ("passive", "Passivo"),
    "DIRECIONAL": ("directional", "Direcional"),
    "ÁREA": ("area", "Área"),
    "ÁREA ESTENDIDA": ("extended-area", "Área Estendida"),
    "PSÍQUICO": ("psychic", "Psíquico"),
    "ÓBVIO": ("obvious", "Óbvio"),
    "REALISTA": ("realistic", "Realista"),
    "SENTIDO ÚNICO": ("single-sense", "Sentido Único"),
    "MULTISSENTIDOS": ("multi-sense", "Multissentidos"),
    "AMBIENTAL": ("environmental", "Ambiental"),
    "MENTAL": ("mental", "Mental"),
    "FÍSICO": ("physical", "Físico"),
    # A introdução da categoria define "Danoso"; o cabeçalho de Arremessar usa "DANO".
    "DANO": ("damaging", "Danoso"),
    "ESSÊNCIA": ("essence", "Essência"),
}

SPELL_PARAMETERS = {"Forma de Vida": "lifeform", "Objeto": "object", "Atributo": "attribute"}

# (id, nome, categoria, elemento dos feitiços elementais)
SPELLS = [
    ("shatter", "Estilhaçar", "combat", None),
    ("powerbolt", "Raio de Força", "combat", None),
    ("powerball", "Esfera de Força", "combat", None),
    ("acid-stream", "Jato de Ácido", "combat", "acid"),
    ("toxic-wave", "Onda Tóxica", "combat", "acid"),
    ("flamethrower", "Lança-Chamas", "combat", "fire"),
    ("fireball", "Bola de Fogo", "combat", "fire"),
    ("knockout", "Nocaute", "combat", None),
    ("stunbolt", "Raio de Atordoamento", "combat", None),
    ("stunball", "Esfera de Atordoamento", "combat", None),
    ("lightning-bolt", "Relâmpago", "combat", "electricity"),
    ("ball-lightning", "Esfera de Relâmpago", "combat", "electricity"),
    ("punch", "Soco", "combat", None),
    ("clout", "Pancada", "combat", None),
    ("blast", "Explosão", "combat", None),
    ("death-touch", "Toque da Morte", "combat", None),
    ("manabolt", "Raio de Mana", "combat", None),
    ("manaball", "Bola de Mana", "combat", None),
    ("analyze-device", "Analisar Dispositivo", "detection", None),
    ("analyze-magic", "Analisar Magia", "detection", None),
    ("analyze-truth", "Analisar Verdade", "detection", None),
    ("clairaudience", "Clariaudiência", "detection", None),
    ("clairvoyance", "Clarividência", "detection", None),
    ("detect-life-form", "Detectar [Forma de Vida]", "detection", None),
    ("detect-life-form-extended", "Detectar [Forma de Vida], Estendido", "detection", None),
    ("detect-object", "Detectar [Objeto]", "detection", None),
    ("detect-individual", "Detectar Indivíduo", "detection", None),
    ("detect-enemies", "Detectar Inimigos", "detection", None),
    ("detect-enemies-extended", "Detectar Inimigos, Estendido", "detection", None),
    ("detect-magic", "Detectar Magia", "detection", None),
    ("detect-magic-extended", "Detectar Magia, Estendido", "detection", None),
    ("detect-life", "Detectar Vida", "detection", None),
    ("detect-life-extended", "Detectar Vida, Estendido", "detection", None),
    ("mindlink", "Elo Mental", "detection", None),
    ("combat-sense", "Sentido de Combate", "detection", None),
    ("mind-probe", "Sonda Mental", "detection", None),
    ("hush", "Abafar", "illusion", None),
    ("silence", "Silenciar", "illusion", None),
    ("agony", "Agonia", "illusion", None),
    ("mass-agony", "Agonia em Massa", "illusion", None),
    ("confusion", "Confusão", "illusion", None),
    ("mass-confusion", "Confusão em Massa", "illusion", None),
    ("chaos", "Caos", "illusion", None),
    ("chaotic-world", "Mundo Caótico", "illusion", None),
    ("entertainment", "Entretenimento", "illusion", None),
    ("trid-entertainment", "Entretenimento de Trídeo", "illusion", None),
    ("phantasm", "Fantasma", "illusion", None),
    ("trid-phantasm", "Fantasma de Trídeo", "illusion", None),
    ("stealth", "Furtividade", "illusion", None),
    ("bugs", "Insetos", "illusion", None),
    ("swarm", "Enxame", "illusion", None),
    ("invisibility", "Invisibilidade", "illusion", None),
    ("improved-invisibility", "Invisibilidade Melhorada", "illusion", None),
    ("mask", "Máscara", "illusion", None),
    ("physical-mask", "Máscara Física", "illusion", None),
    ("animate", "Animar", "manipulation", None),
    ("mass-animate", "Animar em Massa", "manipulation", None),
    ("armor", "Armadura", "manipulation", None),
    ("fling", "Arremessar", "manipulation", None),
    ("mana-barrier", "Barreira de Mana", "manipulation", None),
    ("physical-barrier", "Barreira Física", "manipulation", None),
    ("ice-sheet", "Camada de Gelo", "manipulation", None),
    ("control-actions", "Controlar Ações", "manipulation", None),
    ("mob-control", "Controle de Multidão", "manipulation", None),
    ("control-thoughts", "Controlar Pensamentos", "manipulation", None),
    ("mob-mind", "Mente da Multidão", "manipulation", None),
    ("magic-fingers", "Dedos Mágicos", "manipulation", None),
    ("ignite", "Inflamar", "manipulation", None),
    ("influence", "Influência", "manipulation", None),
    ("levitate", "Levitação", "manipulation", None),
    ("light", "Luz", "manipulation", None),
    ("poltergeist", "Poltergeist", "manipulation", None),
    ("shadow", "Sombra", "manipulation", None),
    ("antidote", "Antídoto", "health", None),
    ("increase-attribute", "Aumentar [Atributo]", "health", None),
    ("increase-reflexes", "Aumentar Reflexos", "health", None),
    ("heal", "Cura", "health", None),
    ("cure-disease", "Curar Doença", "health", None),
    ("detox", "Desintoxicação", "health", None),
    ("stabilize", "Estabilizar", "health", None),
    ("oxygenate", "Oxigenar", "health", None),
    ("prophylaxis", "Profilaxia", "health", None),
    ("decrease-attribute", "Reduzir [Atributo]", "health", None),
    ("resist-pain", "Resistir à Dor", "health", None),
]

ELEMENTS = {"acid": ("Ácido", "dano de Ácido"), "fire": ("Fogo", "dano de Fogo"),
            "electricity": ("Eletricidade", "dano de Eletricidade")}

RITUAL_KEYWORDS = [("anchored", "Ancorado"), ("material-link", "Elo Material"), ("spell", "Feitiço"),
                   ("minion", "Lacaio"), ("spotter", "Olheiro")]

RITUALS = [
    ("curse", "Maldição"),
    ("prodigal-spell", "Feitiço Abundante"),
    ("remote-sensing", "Sentido Remoto"),
    ("ward", "Proteção"),
    ("circle-of-protection", "Círculo de Proteção"),
    ("circle-of-healing", "Círculo da Cura"),
    ("renascence", "Renascença"),
    ("watcher", "Vigia"),
    ("homunculus", "Homúnculo"),
]

PREPARATION_TRIGGERS = [("command", "Comando", 2), ("contact", "Contato", 1), ("time", "Tempo", 2)]


PHYSICAL_ATTRIBUTES = ["bod", "agi", "rea", "str"]

# (id, nome, parâmetro escolhido na compra, nível máximo próprio, modificadores)
ADEPT_POWERS = [
    ("attribute-boost", "Ampliar Atributo", {"kind": "attribute", "options": PHYSICAL_ATTRIBUTES}, None, []),
    ("missile-parry", "Aparar Projétil", None, None, []),
    ("mystic-armor", "Armadura Mística", None, None, [{"target": "armor", "add": ref("rating")}]),
    ("improved-physical-attribute", "Atributo Físico Melhorado",
     {"kind": "attribute", "options": PHYSICAL_ATTRIBUTES}, None,
     [{"target": "attr", "of": "parameter", "add": ref("rating")}]),
    ("kinesics", "Cinésica", None, None, []),
    ("voice-control", "Controle Vocal", None, None, [{"target": "limit", "of": "social", "add": ref("rating")}]),
    ("light-body", "Corpo Leve", None, None, []),
    ("wall-running", "Correr na Parede", None, None, []),
    ("rapid-healing", "Cura Rápida", None, None, []),
    ("critical-strike", "Golpe Crítico",
     {"kind": "skill", "options": ["unarmed-combat", "clubs", "blades", "astral-combat", "exotic-melee-weapon"]},
     None, [{"target": "weapon.damage", "of": "parameter", "add": 1}]),
    ("improved-ability", "Habilidade Melhorada",
     {"kind": "skill", "categories": ["combat", "physical", "social", "technical", "vehicle"]}, None,
     [{"target": "skill.rating", "of": "parameter", "add": ref("rating")}]),
    ("natural-immunity", "Imunidade Natural", None, None, []),
    ("killing-hands", "Mãos Letais", None, None, []),
    ("traceless-walk", "Passos sem Pegadas", None, None, []),
    ("enhanced-perception", "Percepção Ampliada", None, None, []),
    ("astral-perception", "Percepção Astral", None, None, []),
    ("enhanced-potential", "Potencial Melhorado", {"kind": "limit"}, None,
     [{"target": "limit", "of": "parameter", "add": 1}]),
    ("enhanced-accuracy", "Precisão Ampliada", {"kind": "skill", "categories": ["combat"], "except": ["unarmed-combat"]},
     None, [{"target": "weapon.accuracy", "of": "parameter", "add": 1}]),
    ("adrenaline-boost", "Pulso de Adrenalina", None, None, []),
    ("improved-reflexes", "Reflexos Melhorados", None, 3,
     [{"target": "attr", "of": "rea", "add": ref("rating")}, {"target": "initiative.dice", "add": ref("rating")}]),
    ("pain-resistance", "Resistência à Dor", None, None, [{"target": "wound.ignoredBoxes", "add": ref("rating")}]),
    ("spell-resistance", "Resistência a Feitiços", None, None, []),
    ("combat-sense", "Sentido de Combate", None, None, []),
    ("danger-sense", "Sentido de Perigo", None, None, []),
    ("improved-sense", "Sentido Melhorado", None, None, []),
]

ACTIVATIONS = {"Ação Simples": "simple", "Ação Livre": "free",
               "Ação de Interrupção (–5 do Valor de Iniciativa)": "interrupt"}


def grant(power, levels=None, **extra):
    return {"power": power, **({"levels": levels} if levels else {}), **extra}


# (id, nome, poderes gratuitos de adepto, qualidade imposta pela desvantagem)
MENTORS = [
    ("eagle", "Águia", [grant("combat-sense", 1)],
     {"quality": "allergy", "options": {"prevalence": "common", "severity": "moderate"}, "karma": 0,
      "note": "Alergia a poluentes, sem o bônus de carma"}),
    ("dog", "Cão", [grant("improved-sense", count=2)], None),
    ("raven", "Corvo", [grant("traceless-walk"), grant("voice-control", 1)], None),
    ("cat", "Gato", [grant("light-body", 2)], None),
    ("wise-warrior", "Guerreiro Sábio", [grant("improved-ability", 1, parameter={"categories": ["combat"]})], None),
    ("wolf", "Lobo", [grant("attribute-boost", 2, parameter="agi")], None),
    # "Uma perícia atlética" é lida como uma perícia do grupo Atletismo.
    ("sea", "Mar", [grant("improved-ability", 1, parameter={"groups": ["athletics"]})], None),
    # O livro diz "1 nível gratuito de Precisão Ampliada", mas o poder tem custo
    # fixo por perícia, sem níveis.
    ("dragonslayer", "Matador de Dragões", [grant("enhanced-accuracy"), grant("danger-sense", 1)], None),
    ("mountain", "Montanha", [grant("mystic-armor", 1)], None),
    ("thunderbird", "Pássaro-Trovão", [grant("critical-strike")], None),
    ("fire-bringer", "Portador da Chama",
     [grant("improved-ability", 1, parameter={"exceptCategories": ["combat"]})], None),
    ("rat", "Rato", [grant("natural-immunity", 2)], None),
    ("seducer", "Sedutor", [grant("improved-ability", 1, parameter={"groups": ["acting", "influence"]})], None),
    ("serpent", "Serpente", [grant("kinesics", 2)], None),
    ("shark", "Tubarão", [grant("killing-hands")], None),
    ("bear", "Urso", [grant("rapid-healing", 1)], None),
]


COMPLEX_FORMS = [
    ("static-bomb", "Bomba de Estática"),
    ("resonance-channel", "Canal de Ressonância"),
    ("tattletale", "Difamador"),
    ("diffusion", "Difusão de [Atributo da Matriz]"),
    ("editor", "Editor"),
    ("resonance-spike", "Ferrão de Ressonância"),
    ("transcendent-grid", "Grade Transcendental"),
    ("infusion", "Infusão de [Atributo da Matriz]"),
    ("cleaner", "Limpador"),
    ("stitches", "Sutura"),
    ("pulse-storm", "Tempestade de Pulso"),
    ("puppeteer", "Titereiro"),
    ("static-veil", "Véu de Estática"),
    ("resonance-veil", "Véu de Ressonância"),
]

COMPLEX_FORM_TARGETS = {"Pessoal": "self", "Dispositivo": "device", "Persona": "persona", "Arquivo": "file",
                        "Sprite": "sprite"}

MATRIX_ATTRIBUTES = [("attack", "Ataque"), ("sleaze", "Subversão"), ("dataProcessing", "Datagrama"),
                     ("firewall", "Firewall")]


# Qualidades cuja compra exige escolher um item de outro catálogo.
QUALITY_CHOICES = {"spirit-affinity": "traditions.json#spiritTypes",
                   "mentor-spirit": "mentors.json#mentors"}


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


def flow(book, first, last, sidebars):
    """Linhas (página, texto) das páginas first..last sem os boxes laterais.

    sidebars mapeia página -> (primeira linha, última linha ou None para ir até
    o fim da página); o texto de cada box volta à parte, por página.
    """
    lines, boxes = [], {}
    for p in range(first, last + 1):
        page = book.page(p).split("\n")
        if p in sidebars:
            start, end = sidebars[p]
            i = next((k for k, line in enumerate(page) if line.strip().startswith(start)), None)
            j = len(page) - 1 if end is None else next(
                (k for k, line in enumerate(page) if line.strip().startswith(end)), None)
            if i is None or j is None:
                raise ExtractionError(f"box lateral da p. {p} não encontrado: {start!r}")
            boxes[p] = "\n".join(page[i:j + 1])
            page = page[:i] + page[j + 1:]
        lines += [(p, line) for line in page]
    return lines, boxes


def fold(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def heading_re(heading):
    """Cabeçalho em linha própria, tolerando quebra de linha entre as palavras."""
    return re.compile(r'^' + r'\s+'.join(map(re.escape, heading.split())) + r'\s*$', re.M)


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


def build_skills(book):
    numbered, _ = flow(book, 130, 150, SKILL_SIDEBARS)
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


def quality_blocks(lines):
    """{cabeçalho: (linha de custo, página, linhas do corpo)}."""
    costs = [k for k, (_, line) in enumerate(lines) if QUALITY_COST.match(line)]
    heads = []
    for k in costs:
        n = 2 if lines[k - 2][1].endswith("/") else 1
        heads.append((k - n, " ".join(lines[i][1].strip() for i in range(k - n, k)).replace("/ ", "/")))
    blocks = {}
    for n, k in enumerate(costs):
        end = heads[n + 1][0] if n + 1 < len(costs) else len(lines)
        body = [line for _, line in lines[k + 1:end]]
        while body and is_heading(body[-1]):  # "QUALIDADES NEGATIVAS" no fim da última positiva
            body.pop()
        blocks[fold(heads[n][1]).upper()] = (lines[k][1], lines[heads[n][0]][0], body)
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
    lines, boxes = flow(book, 71, 87, QUALITY_SIDEBARS)
    blocks = quality_blocks(lines)
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
            if qid in QUALITY_CHOICES:
                entry["choice"] = QUALITY_CHOICES[qid]
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


def build_lifestyles(book):
    p95 = book.page(95)
    text = book.text(369, 370)
    out = []
    for lid, name, heading, table_name in LIFESTYLES:
        cost = re.search(rf'^{name} (Grátis|[\d.]+¥)$', p95, re.M)
        nuyen = re.search(rf'^{table_name} (\d)D6 x ([\d.]+)¥$', p95, re.M)
        if not cost or not nuyen:
            raise ExtractionError(f"estilo de vida {name}: linha das tabelas da p. 95 não encontrada")
        monthly = 0 if cost.group(1) == "Grátis" else int(cost.group(1)[:-1].replace(".", ""))
        body = section(text, f"\n{heading}\n", [r'^Custo:'])
        if body is None:
            raise ExtractionError(f"estilo de vida {name}: descrição não encontrada nas p. 369–370")
        cost_line = section(text, f"\n{heading}\n", [r'\n[A-ZÁÉÍÓÚÂÊÔÃÕÇ/ ]{4,}\n'])
        if monthly and money(monthly).replace("¥", " neoienes") not in book.prose(cost_line):
            raise ExtractionError(f"estilo de vida {name}: custo da p. 95 diverge da descrição")
        out.append({"id": lid, "name": name, "cost": monthly,
                    "startingNuyen": {"dice": int(nuyen.group(1)), "multiplier": int(nuyen.group(2).replace(".", ""))},
                    "desc": book.prose(body), "page": 369})

    hospital = book.prose(section(text, "\nHOSPITALIZADO\n", [r'^OPÇÕES DE ESTILO']) or "")
    require(hospital, "Custo: 500 neoienes por dia pelo atendimento básico, 1.000 neoienes por tratamento intensivo",
            "estilo de vida Hospitalizado")
    out.append({"id": "hospitalized", "name": "Hospitalizado", "primary": False,
                "costPerDay": {"basic": 500, "intensive": 1000},
                "desc": hospital.split(" Custo:")[0], "page": 369})

    opts = []
    headings = [h for _, _, h, _, _ in LIFESTYLE_OPTIONS] + ["PAGANDO AS CONTAS"]
    for oid, name, heading, cost, cost_text in LIFESTYLE_OPTIONS:
        body = section(text, heading_re(heading), [heading_re(h).pattern for h in headings if h != heading])
        if body is None:
            raise ExtractionError(f"opção de estilo de vida {name}: não encontrada na p. 370")
        body = book.prose(body)
        require(body, f"Custo: {cost_text}", f"opção de estilo de vida {name}")
        opts.append({"id": oid, "name": name, "cost": cost, "desc": body.split(" Custo:")[0], "page": 370})

    rules = book.prose(text + "\n" + book.page(371))
    require(rules, "pagamento equivalente a 100 meses de aluguel", "estilo de vida permanente")
    require(rules, "O custo é dez por cento extra por pessoa adicional", "estilo de vida de equipe")
    require(book.prose(book.text(94, 95)), "Os neoienes restantes acima de 5.000 são perdidos",
            "neoienes iniciais")

    identities = []
    p442 = book.page(442)
    for iid, name, row, unit in IDENTITIES:
        require(p442, row, f"identidade {name}")
        identities.append({"id": iid, "name": name, "rating": {"min": 1, "max": 6},
                           "availability": {"value": mul(ref("rating"), 3), "legality": "P"},
                           "cost": mul(ref("rating"), unit), "page": 442})

    return {"lifestyles": out, "options": opts,
            "rules": {"teamPercentPerExtraPerson": 10, "permanentMonths": 100},
            "identities": identities}


def build_mechanics(book):
    p101 = book.prose(book.page(101))
    for fragment in ["Iniciativa (Intuição + Reação) + 1D6", "Iniciativa Astral (Intuição x 2) + 2D6",
                     "Iniciativa de RA da Matriz (Intuição + Reação) + 1D6",
                     "(Sim Fechado)(Datagrama + Intuição) + 3D6", "(Sim Aberto)(Datagrama + Intuição) + 4D6",
                     "Mental [(Lógica x 2) + Intuição + Vontade] / 3 (arredonde para cima)",
                     "Físico [(Força x 2) + Corpo + Reação] / 3 (arredonde para cima)",
                     "Social [(Carisma x 2) + Vontade + Essência] / 3 (arredonde para cima)",
                     "Físico [Corpo / 2] + 8", "Atordoamento [Vontade / 2] + 8", "Excesso Corpo + bônus de Ampliação",
                     "Ataque Carisma", "Datagrama Lógica", "Nível de Dispositivo Ressonância", "Firewall Vontade",
                     "Subversão Intuição"]:
        require(p101, fragment, "Tabela de Cálculos Finais (p. 101)")
    require(book.prose(book.page(100)), "arredonde a Essência para cima", "limite Social")
    require(book.prose(book.page(52)), "Todos têm um e podem conseguir até mais quatro (para um total de cinco)",
            "dados de iniciativa")
    p152 = book.page(152)
    for fragment in ["COMPOSTURA (CAR + VON)", "JULGAR INTENÇÕES (CAR + INT)", "ERGUER/CARREGAR (COR + FOR)",
                     "MEMÓRIA (LOG + VON)"]:
        require(p152, fragment, "testes apenas de atributos (p. 152)")
    p152 = book.prose(p152)
    for fragment in ["15 quilogramas por ponto de Força", "5 quilogramas por ponto de Força",
                     "Força x 10 quilogramas"]:
        require(p152, fragment, "erguer/carregar (p. 152)")
    require(book.page(162), "Agilidade x 2 Agilidade x 4", "movimento")
    p368 = book.prose(book.page(368))
    require(p368, "o Crédito de Rua é igual ao Carma total da personagem, dividido por 10, sempre arredondando "
                  "para baixo", "crédito de rua")
    require(p368, "mínimo de 0", "notoriedade")

    p98 = book.prose(book.page(98))
    for fragment in ["o excedente máximo seja de 7 Carma", "Níveis de Dispositivo 6 ou menos ou Disponibilidade 12 "
                     "ou menos", "igual ao nível de Carisma do personagem x 3", "4 Carma por forma complexa",
                     "5 Carma por feitiço", "1 Carma por serviço", "1 Carma por tarefa",
                     "não pode ter mais do que 7 Carma"]:
        require(p98, fragment, "compras com carma (p. 98)")
    p71 = book.prose(book.page(71))
    require(p71, "o personagem começa o processo de criação com 25 de Carma", "carma inicial")
    require(p71, "Qualidades Positivas que custe 25 de Carma e de Qualidades Negativas que rendam 25 de Carma",
            "teto de qualidades")
    require(book.prose(book.text(94, 95)), "2.000 neoienes por ponto de Carma", "conversão de carma")
    require(book.prose(book.page(94)), "o bônus máximo para um atributo é sempre +4", "ampliação máxima")

    mechanics = {
        "expressions": {
            "ops": sorted(OPS),
            "refs": {
                "attr.<id>": "Valor atual do atributo, já com ampliações",
                "rating": "Nível do item, da qualidade ou do nível novo sendo comprado",
                "grade": "Classe de iniciação ou submersão",
                "karma.total": "Carma total ganho pelo personagem",
                "quality.karma": "Custo ou bônus de carma da qualidade",
                "matrix.dataProcessing": "Datagrama da persona em uso (ciberdeck, com-link ou persona viva)",
                "force": "Potência do feitiço, ritual ou preparação",
                "netHits": "Sucessos restantes do teste",
            },
        },
        "derived": {
            "initiative": {
                "physical": {"name": "Iniciativa", "base": add(attr("rea"), attr("int")), "dice": 1},
                "astral": {"name": "Iniciativa Astral", "base": mul(attr("int"), 2), "dice": 2},
                "matrixAR": {"name": "Iniciativa de RA da Matriz", "base": add(attr("rea"), attr("int")), "dice": 1},
                "matrixVRCold": {"name": "Iniciativa de RV da Matriz (Sim Fechado)",
                                 "base": add(ref("matrix.dataProcessing"), attr("int")), "dice": 3},
                "matrixVRHot": {"name": "Iniciativa de RV da Matriz (Sim Aberto)",
                                "base": add(ref("matrix.dataProcessing"), attr("int")), "dice": 4},
                "maxDice": 5,
                "page": 101,
            },
            "limits": {
                "physical": {"name": "Limite Físico",
                             "value": ceil(div(add(mul(attr("str"), 2), attr("bod"), attr("rea")), 3))},
                "mental": {"name": "Limite Mental",
                           "value": ceil(div(add(mul(attr("log"), 2), attr("int"), attr("wil")), 3))},
                "social": {"name": "Limite Social",
                           "value": ceil(div(add(mul(attr("cha"), 2), attr("wil"), ceil(attr("ess"))), 3))},
                "page": 101,
            },
            "monitors": {
                "physical": {"name": "Monitor de Condição Física", "boxes": add(ceil(div(attr("bod"), 2)), 8)},
                "stun": {"name": "Monitor de Condição de Atordoamento", "boxes": add(ceil(div(attr("wil"), 2)), 8)},
                "overflow": {"name": "Excesso", "boxes": attr("bod")},
                "wounds": {"boxesPerPenalty": 3, "penalty": -1},
                "page": 101,
            },
            "attributeTests": {
                "composure": {"name": "Compostura", "pool": add(attr("cha"), attr("wil"))},
                "judgeIntentions": {"name": "Julgar Intenções", "pool": add(attr("cha"), attr("int"))},
                "memory": {"name": "Memória", "pool": add(attr("log"), attr("wil"))},
                "liftCarry": {"name": "Erguer/Carregar", "pool": add(attr("bod"), attr("str"))},
                "page": 152,
            },
            "lifting": {"unit": "kg", "lift": mul(attr("str"), 15), "overhead": mul(attr("str"), 5),
                        "carry": mul(attr("str"), 10), "page": 152},
            "movement": {"unit": "m por Turno de Combate", "walk": mul(attr("agi"), 2), "run": mul(attr("agi"), 4),
                         "sprint": "metatypes.json#metatypes", "page": 162},
            "livingPersona": {
                "attack": attr("cha"), "sleaze": attr("int"), "dataProcessing": attr("log"),
                "firewall": attr("wil"), "deviceRating": attr("res"), "page": 101,
            },
            "reputation": {
                "streetCred": {"name": "Crédito de Rua", "value": floor(div(ref("karma.total"), 10))},
                "notoriety": {"name": "Notoriedade", "base": 0, "min": 0,
                              "note": "Some os modificadores reputation.notoriety das qualidades"},
                "publicAwareness": {"name": "Consciência Pública", "base": 0},
                "page": 368,
            },
        },
        "creation": {
            "karma": 25,
            "qualities": {"positiveMax": 25, "negativeMax": 25},
            "attributes": {"atNaturalMaxMax": 1, "pointsPerRating": 1,
                           "note": "Só um atributo Físico ou Mental pode começar no máximo natural; "
                                   "Trunfo, Magia e Ressonância não contam."},
            "specialAttributes": ["edg", "mag", "res"],
            "skills": {"maxRating": 6, "specializationsPerSkill": 1, "specializationCost": 1,
                       "knowledgeMaxRating": 6,
                       "knowledgePoints": mul(add(attr("int"), attr("log")), 2)},
            "contacts": {"karma": mul(attr("cha"), 3), "minConnection": 1, "minLoyalty": 1, "minKarma": 2,
                         "maxKarmaPerContact": 7},
            "resources": {"karmaToNuyen": {"rate": 2000, "maxKarma": 10}, "nuyenCarryOver": 5000,
                          "maxAvailability": 12, "maxDeviceRating": 6},
            "karmaCarryOver": 7,
            "purchases": {
                "spell": {"karma": 5, "max": mul(attr("mag"), 2)},
                "complexForm": {"karma": 4, "max": mul(attr("res"), 2)},
                "boundSpiritService": {"karma": 1, "maxSpirits": attr("cha"), "force": attr("mag")},
                "registeredSpriteTask": {"karma": 1, "maxSprites": attr("cha"), "level": attr("res")},
                "fociForceMax": mul(attr("mag"), 2),
                "powerPoint": {"karma": 5, "max": attr("mag"), "only": "mystic-adept"},
            },
            "page": 62,
        },
        "progression": {
            "costs": {
                "attribute": mul(ref("rating"), 5),
                "activeSkill": mul(ref("rating"), 2),
                "skillGroup": mul(ref("rating"), 5),
                "knowledgeSkill": ref("rating"),
                "languageSkill": ref("rating"),
                "specialization": 7,
                "newKnowledgeOrLanguage": 1,
                "positiveQuality": mul(ref("quality.karma"), 2),
                "removeNegativeQuality": mul(ref("quality.karma"), 2),
                "spell": 5,
                "complexForm": 4,
                "initiation": add(10, mul(ref("grade"), 3)),
                "submersion": add(10, mul(ref("grade"), 3)),
                "note": "Custo para subir ao nível rating a partir do anterior; comprar vários níveis soma os degraus.",
            },
            "maxRating": {"skill": 12, "skillAptitude": 13},
            "perDowntime": {"attributeRatings": 2, "skillRatings": 3, "skillGroupRatings": 1},
            "training": {
                "attribute": {"unit": "week", "time": ref("rating")},
                "edge": None,
                "skill": [{"ratings": [1, 4], "unit": "day", "time": ref("rating")},
                          {"ratings": [5, 8], "unit": "week", "time": ref("rating")},
                          {"ratings": [9, 13], "unit": "week", "time": mul(ref("rating"), 2)}],
                "skillGroup": {"unit": "week", "time": mul(ref("rating"), 2)},
                "specialization": {"unit": "month", "time": 1},
                "instructorReduction": 0.25,
            },
            "page": 103,
        },
        "augmentation": {"maxAttributeBonus": 4, "page": 94},
        "legality": {"R": "Restrito", "P": "Proibido"},
    }
    check_progression(book, mechanics["progression"]["costs"])
    return mechanics


def check_progression(book, costs):
    text = book.page(107)
    for row in re.finditer(r'^(\d+)((?: (?:\d+|—)){10})\s*$', text, re.M):
        start = int(row.group(1))
        for target, cell in zip(range(2, 12), row.group(2).split()):
            if cell == "—":
                continue
            total = sum(evaluate(costs["attribute"], {"rating": r}) for r in range(start + 1, target + 1))
            if total != int(cell):
                raise ExtractionError(f"progressão de atributo {start}→{target}: livro {cell}, fórmula {total}")
    # Rótulos como saem do PDF: "Grupo de Perícias / Ativas" e "Perícias de /
    # Conhecimento" quebram a linha antes dos números.
    rows = {"Perícia Ativa": "activeSkill", "Ativas": "skillGroup", "Conhecimento": "knowledgeSkill",
            "Perícias de Idioma": "languageSkill"}
    for label, key in rows.items():
        m = re.search(rf'^{label} ((?:\d+ ){{11}}\d+)(?: (\d+|—))?\s*$', text, re.M)
        if not m:
            raise ExtractionError(f"progressão: linha {label!r} não encontrada na p. 107")
        cells = [int(c) for c in m.group(1).split()] + ([int(m.group(2))] if m.group(2) not in (None, "—") else [])
        for rating, cell in enumerate(cells, 1):
            total = sum(evaluate(costs[key], {"rating": r}) for r in range(1, rating + 1))
            if total != cell:
                raise ExtractionError(f"progressão {label} nível {rating}: livro {cell}, fórmula {total}")


def build_traditions(book):
    sidebars = {279: ("TRADIÇÃO HERMÉTICA", None), 280: ("TRADIÇÃO XAMÂNICA", None)}
    lines, boxes = flow(book, 279, 280, sidebars)
    text = "\n".join(line for _, line in lines)
    intro = section(text, "\nTRADIÇÕES\n", [r'^O MAGO HERMÉTICO$'])
    if intro is None:
        raise ExtractionError("tradições: introdução não encontrada na p. 279")
    require(book.prose(intro), "Seguidores da tradição hermética são chamados de magos, enquanto seguidores da "
            "tradição xamânica são chamados de xamãs", "tradições")

    spirit_by_name = {name: sid for sid, name in SPIRIT_TYPES}
    headings = [h for *_, h, _, _ in TRADITIONS]
    out = []
    for (tid, name, box_title, heading, followers, drain), box in zip(TRADITIONS, boxes.values()):
        box = book.prose(box)
        if not box.startswith(box_title):
            raise ExtractionError(f"tradição {name}: box {box_title!r} fora do lugar")
        spirits = {}
        for cid, cname in SPELL_CATEGORIES:
            m = re.search(rf'{cname}: (\w+)', box)
            if not m or m.group(1) not in spirit_by_name:
                raise ExtractionError(f"tradição {name}: espírito de {cname} ilegível")
            spirits[cid] = spirit_by_name[m.group(1)]
        m = re.search(r'Dreno: (\w+) \+ (\w+)', box)
        if not m or [fold(a) for a in m.groups()] != [fold(ATTRIBUTE_NAMES[a]) for a in drain]:
            raise ExtractionError(f"tradição {name}: dreno no livro {m and m.group(0)!r}, vocabulário {drain}")

        body = section(text, f"\n{heading}\n", [rf'^{h}$' for h in headings if h != heading]
                       + [r'^ESTÂNCIAS$'])
        if body is None:
            raise ExtractionError(f"tradição {name}: seção {heading!r} não encontrada")
        out.append({"id": tid, "name": name, "followers": followers,
                    "drain": add(attr(drain[0]), attr(drain[1])), "spirits": spirits,
                    "desc": book.prose(body), "page": 279})

    return {"desc": book.prose(intro),
            "spiritTypes": [{"id": sid, "name": name} for sid, name in SPIRIT_TYPES],
            "traditions": out}


SPELL_SIDEBARS = {
    283: ("EXEMPLO", None),
    285: ("EXEMPLO", None),
    286: ("RESULTADOS DE", None),
    287: ("TABELA DE SONDA MENTAL", None),
}
SPELL_TYPE = re.compile(r'^Tipo:\s*([FM])\s+Alcance:\s*(LDV|T)\s*(\(A\))?(?:\s+Dano:\s*([FA]))?$')
SPELL_DURATION = re.compile(r'^Duração:\s*([ISP])\s+Dreno:\s*P\s*(?:([–+-])\s*(\d+))?$')
DURATIONS = {"I": "instant", "S": "sustained", "P": "permanent"}


def potency_formula(sign, amount, ref_name):
    """'P – 3' / 'N + 1' viram fórmula sobre a Potência ou o Nível."""
    if not sign:
        return ref(ref_name)
    return op("sub" if sign in "–-" else "add", ref(ref_name), int(amount))


def results_table(text, where):
    """Linhas "sucessos restantes → resultado" de uma tabela achatada."""
    rows = []
    for m in re.finditer(r'(?:^| )(\d)(?:–(\d)|(\+))? (.+?)(?= \d(?:–\d|\+)? [A-Z]|$)', text):
        low = int(m.group(1))
        high = int(m.group(2)) if m.group(2) else (None if m.group(3) else low)
        rows.append({"netHits": {"min": low, "max": high}, "result": m.group(4).strip()})
    if not rows or rows[0]["netHits"]["min"] != 1:
        raise ExtractionError(f"{where}: tabela de resultados ilegível")
    return rows


def build_spells(book):
    lines, boxes = flow(book, 283, 294, SPELL_SIDEBARS)
    texts = [line.strip() for _, line in lines]
    texts = texts[texts.index("FEITIÇOS DE COMBATE"):texts.index("CONTRAMÁGICA")]
    pages = [p for p, _ in lines][[line.strip() for _, line in lines].index("FEITIÇOS DE COMBATE"):]

    category_by_heading = {f"FEITIÇOS DE {name.upper()}": cid for cid, name in SPELL_CATEGORIES}
    headings = {i: category_by_heading[t] for i, t in enumerate(texts) if t in category_by_heading}

    blocks = []
    for k, t in enumerate(texts):
        if not t.startswith("Tipo:"):
            continue
        kw = texts[k - 1] if texts[k - 1].startswith("(") else None
        end = k - 1 if kw else k
        start = end - 1
        if texts[start - 1].endswith(","):
            start -= 1
        blocks.append({"start": start, "name": " ".join(texts[start:end]), "keywords": kw, "type": t,
                       "duration": texts[k + 1], "body": k + 2})

    by_name = {fold(name).upper(): (sid, name, cat, element) for sid, name, cat, element in SPELLS}
    stops = sorted(set(headings) | {b["start"] for b in blocks} | {len(texts)})
    spells, pending, intros = [], [], {}
    for b in blocks:
        key = fold(b["name"]).upper()
        if key not in by_name:
            raise ExtractionError(f"feitiço fora do vocabulário: {b['name']!r}")
        sid, name, category, element = by_name.pop(key)
        own = max(i for i in headings if i < b["start"])
        if headings[own] != category:
            raise ExtractionError(f"feitiço {name}: está em {headings[own]}, vocabulário diz {category}")
        if own not in intros:
            first = min(x["start"] for x in blocks if x["start"] > own)
            intros[own] = (category, book.prose("\n".join(texts[own + 1:first])), pages[own])

        m, d = SPELL_TYPE.match(b["type"]), SPELL_DURATION.match(b["duration"])
        if not m or not d:
            raise ExtractionError(f"feitiço {name}: linhas de Tipo/Duração fora do formato")
        keywords = []
        for word in (b["keywords"] or "").strip("()").split(","):
            word = word.strip()
            if not word:
                continue
            if word not in SPELL_KEYWORDS:
                raise ExtractionError(f"feitiço {name}: palavra-chave fora do vocabulário {word!r}")
            keywords.append(SPELL_KEYWORDS[word][0])
        if (category == "combat") != bool(m.group(4)):
            raise ExtractionError(f"feitiço {name}: só feitiços de Combate têm Dano")

        entry = {"id": sid, "name": name, "category": category, "keywords": keywords,
                 "type": "physical" if m.group(1) == "F" else "mana",
                 "range": "los" if m.group(2) == "LDV" else "touch", "area": bool(m.group(3))}
        if m.group(4):
            entry["damage"] = "physical" if m.group(4) == "F" else "stun"
        entry["duration"] = DURATIONS[d.group(1)]
        entry["drain"] = potency_formula(d.group(2), d.group(3), "force")
        param = re.search(r'\[(.+?)\]', name)
        if param:
            entry["parameter"] = {"id": SPELL_PARAMETERS[param.group(1)], "name": param.group(1)}
        if element:
            entry["element"] = element
        entry["page"] = pages[b["start"]]

        stop = min(s for s in stops if s > b["start"])
        body = book.prose("\n".join(texts[b["body"]:stop]))
        pending.append(entry)
        if body:
            for e in pending:
                e["desc"] = body
                spells.append(e)
            pending = []
    if pending or by_name:
        raise ExtractionError(f"feitiços sem descrição ou não encontrados: {[e['id'] for e in pending] + list(by_name)}")

    for e in spells:
        if "element" in e:
            require(e["desc"], ELEMENTS[e["element"]][1], f"feitiço {e['name']}")

    categories = []
    for _, (cid, desc, page) in sorted(intros.items()):
        categories.append({"id": cid, "name": dict(SPELL_CATEGORIES)[cid], "desc": desc, "page": page})
    rules_by_category = {
        "combat": ("Valor de Dano de um feitiço de combate indireto bem-sucedido é Potência + sucessos restantes, "
                   "com um PA igual a –(Potência)",
                   {"direct": {"damage": ref("netHits")},
                    "indirect": {"damage": add(ref("force"), ref("netHits")), "ap": mul(ref("force"), -1)}}),
        "detection": ("Potência do feitiço x Magia do conjurador em metros",
                      {"range": mul(ref("force"), attr("mag")), "extendedRange": mul(ref("force"), attr("mag"), 10)}),
        "manipulation": ("Valor de Dano igual a sua Potência (inalterado pelos sucessos no teste de Conjuração) e 0 PA",
                         {"damaging": {"damage": ref("force"), "ap": 0}}),
    }
    for c in categories:
        if c["id"] in rules_by_category:
            fragment, rules = rules_by_category[c["id"]]
            require(c["desc"], fragment, f"categoria {c['name']}")
            c["rules"] = rules
    detection = next(c for c in categories if c["id"] == "detection")
    table = book.prose(section(boxes[286], "RESULTADOS", [r'\Z']))
    detection["results"] = [dict(r, result=r["result"].split(" Exemplo de Detectar Vida: ")[0],
                                 example=r["result"].split(" Exemplo de Detectar Vida: ")[1])
                            for r in results_table(section(table, "RESULTADOS", [r'\Z']), "Detecção")]
    probe = next(e for e in spells if e["id"] == "mind-probe")
    probe["results"] = results_table(section(book.prose(boxes[287]), "RESULTADOS", [r'\Z']), "Sonda Mental")

    p281, p282 = book.prose(book.page(281)), book.prose(book.page(282) + "\n" + book.page(283))
    require(p281, "Você pode conjurar um feitiço com Potência até o dobro do seu nível de Magia", "potência máxima")
    require(p281, "a área do feitiço é uma esfera centrada no alvo com um raio em metros igual a Potência do feitiço",
            "área de feitiço")
    require(p282, "você sofre –2 de penalidade na pilha de dados em todos os testes enquanto estiver sustentando",
            "feitiço sustentado")
    require(p282, "nunca pode ser menor do que 2", "dreno mínimo")

    return {
        "types": [{"id": "physical", "name": "Físico", "abbr": "F"}, {"id": "mana", "name": "Mana", "abbr": "M"}],
        "ranges": [{"id": "los", "name": "Linha de Visão", "abbr": "LDV"}, {"id": "touch", "name": "Toque", "abbr": "T"}],
        "durations": [{"id": "instant", "name": "Instantâneo", "abbr": "I"},
                      {"id": "sustained", "name": "Sustentado", "abbr": "S"},
                      {"id": "permanent", "name": "Permanente", "abbr": "P"}],
        "damageTypes": [{"id": "physical", "name": "Físico", "abbr": "F"},
                        {"id": "stun", "name": "Atordoamento", "abbr": "A"}],
        "keywords": [{"id": kid, "name": name} for kid, name in dict.fromkeys(SPELL_KEYWORDS.values())],
        "elements": [{"id": eid, "name": name} for eid, (name, _) in ELEMENTS.items()],
        "rules": {"forceMax": mul(attr("mag"), 2), "drainMin": 2, "sustainedPenalty": -2,
                  "areaRadius": ref("force"), "page": 281},
        "categories": categories,
        "spells": spells,
        **build_rituals(book),
        "preparations": build_preparations(book),
    }


def build_rituals(book):
    lines, _ = flow(book, 296, 298, {297: ("ELO MATERIAL", None), 298: ("VIGIAS E HOMÚNCULOS", None)})
    texts = [line.strip() for _, line in lines]
    pages = [p for p, _ in lines]
    start = texts.index("RITUAIS")
    texts, pages = texts[start:texts.index("APRENDENDO FEITIÇOS")], pages[start:]

    heads = []
    for rid, name in RITUALS:
        found = [i for i, t in enumerate(texts) if t == name.upper() and texts[i + 1].startswith("(")]
        if len(found) != 1:
            raise ExtractionError(f"ritual {name}: {len(found)} cabeçalhos encontrados")
        heads.append(found[0])
    if heads != sorted(heads):
        raise ExtractionError("rituais fora da ordem do livro")
    unknown = [t for i, t in enumerate(texts[:-1]) if i > heads[0] and texts[i + 1].startswith("(")
               and is_heading(t) and i not in heads]
    if unknown:
        raise ExtractionError(f"rituais fora do vocabulário: {unknown}")

    intro = book.prose("\n".join(texts[1:heads[0]]))
    names = [name for _, name in RITUAL_KEYWORDS]
    keywords = []
    for kid, name in RITUAL_KEYWORDS:
        m = re.search(rf'{name}: (.+?)(?= (?:{"|".join(names)}): |$)', intro)
        if not m:
            raise ExtractionError(f"palavra-chave de ritual {name}: definição não encontrada")
        keywords.append({"id": kid, "name": name, "desc": m.group(1)})
    by_name = {name.upper(): kid for kid, name in RITUAL_KEYWORDS}

    rituals = []
    for (rid, name), h, nxt in zip(RITUALS, heads, heads[1:] + [len(texts)]):
        words = [w.strip() for w in texts[h + 1].strip("()").split(",")]
        if any(w not in by_name for w in words):
            raise ExtractionError(f"ritual {name}: palavra-chave fora do vocabulário {words}")
        desc = book.prose("\n".join(texts[h + 2:nxt]))
        m = re.search(r'(?:exige|precisa de) \(Potência\) (horas|minutos) para ser', desc)
        if not m:
            raise ExtractionError(f"ritual {name}: tempo de execução não encontrado")
        rituals.append({"id": rid, "name": name, "keywords": [by_name[w] for w in words],
                        "time": {"unit": {"horas": "hour", "minutos": "minute"}[m.group(1)], "value": ref("force")},
                        "desc": desc, "page": pages[h]})
    return {"ritualKeywords": keywords, "rituals": rituals}


def build_preparations(book):
    text = book.prose(book.page(304) + "\n" + book.page(305))
    require(text, "Você pode fazer uma preparação a uma Potência até duas vezes o seu nível de Magia",
            "potência de preparação")
    names = [name for _, name, _ in PREPARATION_TRIGGERS]
    triggers = []
    for tid, name, drain in PREPARATION_TRIGGERS:
        m = re.search(rf'{name}: (.+?)(?= (?:{"|".join(names)}): | ETAPA 5|$)', text)
        if not m:
            raise ExtractionError(f"gatilho de preparação {name}: descrição não encontrada")
        require(m.group(1), f"adiciona +{drain} de Dreno", f"gatilho {name}")
        triggers.append({"id": tid, "name": name, "drainModifier": drain, "desc": m.group(1)})
    return {"forceMax": mul(attr("mag"), 2), "triggers": triggers, "page": 304}


POWER_COST = re.compile(r'^Custo:\s*(.+?)\s*$')


def power_cost(text, box, name):
    m = re.match(r'^([\d.]+) PP( por nível| cada)?$', text)
    if m:
        value = float(m.group(1))
        value = int(value) if value.is_integer() else value
        return {" por nível": {"perLevel": value}, " cada": {"each": value}, None: value}[m.group(2)]
    if text == "Variável, veja tabela":
        levels = re.findall(r'^Nível (\d) ([\d.]+)$', box, re.M)
        if [int(n) for n, _ in levels] != [1, 2, 3]:
            raise ExtractionError(f"poder {name}: tabela de custo ilegível")
        return {"byLevel": [float(c) for _, c in levels]}
    raise ExtractionError(f"poder {name}: custo fora do formato {text!r}")


def build_adept_powers(book):
    lines, boxes = flow(book, 308, 311, {310: ("TABELA DE REFLEXOS MELHORADOS", None)})
    texts = [line.strip() for _, line in lines]
    pages = [p for p, _ in lines]
    start = texts.index("PODERES DE ADEPTO")
    intro = book.prose("\n".join(texts[:start]))
    require(intro, "O número máximo de níveis que pode ter em qualquer poder é igual ao seu Nível de Magia",
            "nível máximo de poder")
    require(intro, "é resistido com Corpo + Vontade", "dreno de adepto")

    costs = [k for k in range(start, len(texts)) if POWER_COST.match(texts[k])]
    heads = []
    for k in costs:
        param = texts[k - 1] if texts[k - 1].startswith("(") else None
        heads.append((k - (2 if param else 1), texts[k - (2 if param else 1)], param))

    by_name = {fold(name).upper(): entry for entry in ADEPT_POWERS for name in [entry[1]]}
    out = []
    for n, (k, (h, heading, param)) in enumerate(zip(costs, heads)):
        key = fold(heading).upper()
        if key not in by_name:
            raise ExtractionError(f"poder de adepto fora do vocabulário: {heading!r}")
        pid, name, parameter, max_level, modifiers = by_name.pop(key)
        if bool(param) != (parameter is not None and pid != "improved-physical-attribute"):
            raise ExtractionError(f"poder {name}: parâmetro no livro {param!r} diverge do vocabulário")

        cost = power_cost(POWER_COST.match(texts[k]).group(1), boxes.get(310, ""), name)
        body = k + 1
        activation = None
        if texts[body].startswith("Ativação:"):
            label = texts[body].split(":", 1)[1].strip()
            if label not in ACTIVATIONS:
                raise ExtractionError(f"poder {name}: ativação fora do vocabulário {label!r}")
            activation = ACTIVATIONS[label]
            body += 1
        end = heads[n + 1][0] if n + 1 < len(heads) else len(texts)

        entry = {"id": pid, "name": name, "powerPoints": cost}
        if max_level:
            entry["levels"] = {"max": max_level}
        if parameter:
            entry["parameter"] = parameter
        if activation:
            entry["activation"] = activation
        if modifiers:
            entry["modifiers"] = modifiers
        entry.update({"desc": book.prose("\n".join(texts[body:end])), "page": pages[h]})
        out.append(entry)
    if by_name:
        raise ExtractionError(f"poderes de adepto não encontrados: {sorted(by_name)}")
    require(out[[p["id"] for p in out].index("improved-reflexes")]["desc"],
            "O nível máximo de Reflexos Melhorados é 3", "Reflexos Melhorados")

    return {
        "activations": [{"id": aid, "name": label} for label, aid in ACTIVATIONS.items()],
        "rules": {"maxLevel": attr("mag"), "drainResistance": add(attr("bod"), attr("wil")), "page": 308},
        "powers": out,
    }


MENTOR_SIDEBARS = {320: ("FOCOS DE QI", None), 321: ("EXEMPLO", None), 322: ("O LADO SOMBRIO", None)}


def build_mentors(book):
    lines, _ = flow(book, 320, 324, MENTOR_SIDEBARS)
    texts = [line.strip() for _, line in lines]
    texts = texts[:texts.index("INICIAÇÃO")]
    pages = [p for p, _ in lines]
    heads = []
    for mid, name, *_ in MENTORS:
        found = [i for i, t in enumerate(texts) if t == name.upper()]
        if len(found) != 1:
            raise ExtractionError(f"mentor {name}: {len(found)} cabeçalhos encontrados")
        heads.append(found[0])
    if heads != sorted(heads):
        raise ExtractionError("mentores fora da ordem do livro")
    known = {name.upper() for _, name, *_ in MENTORS} | {"VANTAGENS", "DESVANTAGENS"}
    unknown = [t for t in texts[heads[0]:] if is_heading(t) and t not in known]
    if unknown:
        raise ExtractionError(f"mentores fora do vocabulário: {unknown}")

    intro = book.prose("\n".join(texts[1:heads[0]]))
    require(intro, "Adeptos místicos devem escolher a vantagem de adepto ou de mago quando aceitam o espírito "
            "mentor, e não podem mais mudá-la", "mentores")
    power_names = {pid: name for pid, name, *_ in ADEPT_POWERS}

    out = []
    for (mid, name, grants, quality), h, nxt in zip(MENTORS, heads, heads[1:] + [len(texts)]):
        text = book.prose("\n".join(texts[h + 1:nxt]))
        m = re.match(r'(.+?) VANTAGENS Todos: (.+?) Mago: (.+?) Adepto: (.+?) DESVANTAGENS (.+?) '
                     r'Arquétipos Similares: (.+?)$', text)
        if not m:
            raise ExtractionError(f"mentor {name}: blocos Vantagens/Desvantagens fora do formato")
        desc, everyone, magician, adept, drawback, similar = (g.strip() for g in m.groups())
        for g in grants:
            require(fold(adept), fold(power_names[g["power"]]), f"mentor {name}, vantagem de adepto")
            amount = g.get("levels") or g.get("count")
            if amount and not re.search(rf'\b{amount} (?:níveis|nível|poderes)', adept):
                raise ExtractionError(f"mentor {name}: vantagem de adepto não concede {amount} de {g['power']}")
        entry = {"id": mid, "name": name, "desc": desc,
                 "advantages": {"all": everyone, "magician": magician, "adept": adept},
                 "adeptGrants": grants, "disadvantage": drawback}
        if quality:
            require(drawback, "Alergia (poluentes, moderada)", f"mentor {name}")
            entry["disadvantageQuality"] = quality
        entry.update({"similar": [s.strip().rstrip(".") for s in similar.split(",")], "page": pages[h]})
        out.append(entry)

    return {"desc": intro, "rules": {"mysticAdeptChooses": ["magician", "adept"], "page": 320}, "mentors": out}


COMPLEX_FORM_LINE = re.compile(r'^Alvo:\s*(\w+)\s*•\s*Duração:\s*([ISP])\s*•\s*VE:\s*N\s*(?:([–+-])\s*(\d+))?$')


def build_complex_forms(book):
    lines, _ = flow(book, 251, 254, {253: ("EXEMPLO", None)})
    texts = [line.strip() for _, line in lines]
    pages = [p for p, _ in lines]
    end = texts.index("SPRITES")
    anchors = [k for k in range(end) if texts[k].startswith("Alvo:")]
    heads = [k - 2 if texts[k - 1].startswith("[") else k - 1 for k in anchors]

    by_name = {fold(name).upper(): (cid, name) for cid, name in COMPLEX_FORMS}
    out = []
    for n, (k, h) in enumerate(zip(anchors, heads)):
        heading = " ".join(texts[h:k])
        if fold(heading).upper() not in by_name:
            raise ExtractionError(f"forma complexa fora do vocabulário: {heading!r}")
        cid, name = by_name.pop(fold(heading).upper())
        m = COMPLEX_FORM_LINE.match(texts[k])
        if not m or m.group(1) not in COMPLEX_FORM_TARGETS:
            raise ExtractionError(f"forma complexa {name}: linha Alvo/Duração/VE fora do formato")
        entry = {"id": cid, "name": name, "target": COMPLEX_FORM_TARGETS[m.group(1)],
                 "duration": DURATIONS[m.group(2)], "fading": potency_formula(m.group(3), m.group(4), "rating")}
        if "[" in name:
            entry["parameter"] = {"kind": "matrixAttribute", "options": [mid for mid, _ in MATRIX_ATTRIBUTES]}
        stop = heads[n + 1] if n + 1 < len(heads) else end
        entry.update({"desc": book.prose("\n".join(texts[k + 1:stop])), "page": pages[h]})
        out.append(entry)
    if by_name:
        raise ExtractionError(f"formas complexas não encontradas: {sorted(by_name)}")
    for e in out:
        if "parameter" in e:
            require(e["desc"], "uma para cada atributo da Matriz", f"forma complexa {e['name']}")

    rules = book.prose(book.text(251, 252))
    require(rules, "O enfraquecimento é resistido com Ressonância + Vontade", "enfraquecimento")
    require(rules, "Você pode escolher um Nível até três vezes o seu nível de Ressonância", "nível de forma complexa")
    require(rules, "com VD de Enfraquecimento mínimo de 2", "enfraquecimento mínimo")
    require(rules, "impondo –2 de penalidade na pilha de dados em todas as ações por forma complexa sustentada",
            "forma complexa sustentada")
    require(rules, "Você pode conhecer um total de (Ressonância x 2) formas complexas", "formas conhecidas")

    return {
        "targets": [{"id": tid, "name": name} for name, tid in COMPLEX_FORM_TARGETS.items()],
        "matrixAttributes": [{"id": mid, "name": name} for mid, name in MATRIX_ATTRIBUTES],
        "rules": {"levelMax": mul(attr("res"), 3), "knownMax": mul(attr("res"), 2), "fadingMin": 2,
                  "fadingResistance": add(attr("res"), attr("wil")), "sustainedPenalty": -2, "page": 251},
        "complexForms": out,
    }


CATALOGS = {
    "attributes.json": build_attributes,
    "metatypes.json": build_metatypes,
    "priorities.json": build_priorities,
    "awakening.json": build_awakening,
    "skills.json": build_skills,
    "qualities.json": build_qualities,
    "mechanics.json": build_mechanics,
    "lifestyles.json": build_lifestyles,
    "traditions.json": build_traditions,
    "spells.json": build_spells,
    "adept-powers.json": build_adept_powers,
    "mentors.json": build_mentors,
    "complex-forms.json": build_complex_forms,
}

EXPECTED_COUNTS = {
    "attributes.json": {"attributes": 12},
    "metatypes.json": {"metatypes": 5},
    "priorities.json": {"rows": 5},
    "awakening.json": {"awakenings": 5},
    "skills.json": {"skills": 75, "groups": 15},
    "qualities.json": {"qualities": 59},
    "mechanics.json": {},
    "lifestyles.json": {"lifestyles": 7, "options": 5, "identities": 2},
    "traditions.json": {"traditions": 2, "spiritTypes": 6},
    "spells.json": {"spells": 84, "categories": 5, "rituals": 9},
    "adept-powers.json": {"powers": 25},
    "mentors.json": {"mentors": 16},
    "complex-forms.json": {"complexForms": 14},
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
