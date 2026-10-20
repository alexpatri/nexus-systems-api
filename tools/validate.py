#!/usr/bin/env python3
"""Valida os catálogos de um sistema. Sem dependências: python3 validate.py [dir...]"""
import json, math, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent / 'data' / 'systems'

SIZES = {"Miúdo", "Pequeno", "Médio", "Grande", "Enorme", "Imenso"}
DAMAGE_TYPES = {"cortante", "perfurante", "concussão"}
WEAPON_PROPERTIES = {"acuidade", "leve", "pesada", "alcance", "arremesso",
                     "munição", "recarga", "duas mãos", "versátil", "especial"}
ARMOR_CATEGORIES = {"light", "medium", "heavy", "shield"}
WEAPON_CATEGORIES = {"simple-melee", "simple-ranged", "martial-melee", "martial-ranged"}

PENDING = set()  # ids que referenciam dados ainda não extraídos: avisam, não quebram
POINTER = re.compile(r'^[a-z][a-z0-9_-]*\.json(#[A-Za-z0-9_.]+)?$')

def load(d, name):
    p = d / name
    return json.loads(p.read_text()) if p.exists() else None

def resolve(d, pointer):
    """'mechanics.json#dice.approach' -> objeto, ou None se não resolver."""
    fname, _, path = pointer.partition('#')
    obj = load(d, fname)
    if obj is None: return None
    for part in filter(None, path.split('.')):
        if isinstance(obj, dict) and part in obj: obj = obj[part]
        else: return None
    return obj

def walk_strings(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from walk_strings(v, f"{path}[{i}]")
    elif isinstance(o, str):
        yield path, o

def check_vileborn(d, sysj, E, W):
    approaches  = {a['id'] for a in load(d, 'approaches.json')['approaches']}
    conditions  = {c['id'] for c in load(d, 'conditions.json')['conditions']}
    difficulties= {x['id'] for x in load(d, 'difficulties.json')['difficulties']}
    mech = load(d, 'mechanics.json')
    prog = load(d, 'progression.json')
    struct = load(d, 'structure.json')

    # --- catálogos de personagem ---
    for o in load(d, 'origins.json')['origins']:
        for k in ('id','name','summary','approachBonuses','personality','training','chooseIf','abilities'):
            if k not in o: E(f"origem {o['id']}: campo ausente {k}")
        if len(o['approachBonuses']) != 2: E(f"origem {o['id']}: esperado 2 abordagens")
        for a in o['approachBonuses']:
            if a not in approaches: E(f"origem {o['id']}: abordagem inexistente {a}")
        if [x['roll'] for x in o['abilities']] != [1,2,3,4]: E(f"origem {o['id']}: rolls de habilidade")

    heritages = load(d, 'heritages.json')['heritages']
    for h in heritages:
        for k in ('id','name','tagline','summary','kin','approachBonuses','personality',
                  'training','drive','driveMarks','gifts'):
            if k not in h: E(f"herança {h['id']}: campo ausente {k}")
        if len(h['approachBonuses']) != 2: E(f"herança {h['id']}: esperado 2 abordagens")
        for a in h['approachBonuses']:
            if a not in approaches: E(f"herança {h['id']}: abordagem inexistente {a}")
        if [g['roll'] for g in h['gifts']] != list(range(1,10)): E(f"herança {h['id']}: rolls de dom")
        if sorted(h['driveMarks']) != ['0','1','2','3','4+']: E(f"herança {h['id']}: driveMarks incompletos")
        for g in h['gifts']:
            for k in ('id','name','benefit','cost'):
                if not g.get(k): E(f"herança {h['id']} dom {g['roll']}: {k} vazio")

    for c in load(d, 'conditions.json')['conditions']:
        for a in c.get('modifier', {}).get('approaches', []):
            if a not in approaches: E(f"condição {c['id']}: abordagem inexistente {a}")

    # --- mechanics ---
    if mech:
        for scope in ('test', 'reaction'):
            for src in mech[scope].get('pool', []):
                if src.get('blockedBy') and src['blockedBy'] not in conditions:
                    E(f"mechanics.{scope}.pool[{src['id']}]: condição inexistente {src['blockedBy']}")
        for rm in mech['test']['resultModifiers']:
            if rm.get('blockedBy') and rm['blockedBy'] not in conditions:
                E(f"mechanics.test.resultModifiers[{rm['id']}]: condição inexistente {rm['blockedBy']}")
        for ex in mech['reaction']['excludes']:
            if ex not in {s['id'] for s in mech['test']['pool']}:
                E(f"mechanics.reaction.excludes: fonte de dado inexistente {ex}")

        intensities = {i['id'] for i in mech['darkTest']['intensities']}
        he = mech['heritageExploration']
        if sorted(he['marksToIntensity']) != [str(i) for i in range(1, he['markBoxes']+1)]:
            E(f"mechanics.heritageExploration: marksToIntensity não cobre 1..{he['markBoxes']}")
        for k, v in he['marksToIntensity'].items():
            if v not in intensities: E(f"mechanics.heritageExploration.marksToIntensity[{k}]: intensidade inexistente {v}")
        if mech['urge']['resist']['approach'] not in approaches:
            E("mechanics.urge.resist: abordagem inexistente")

        yid = mech['urge']['yield']['id']
        rev = load(d, 'reverie.json')
        clearers = {yid} | ({rev['id']} if rev else set())
        for sec in ('heritageExploration', 'gifts'):
            for c in mech[sec]['clearedBy']:
                if c in clearers: continue
                (W if c in PENDING else E)(f"mechanics.{sec}.clearedBy: {c!r} não resolve")

    # --- structure ---
    if struct:
        scopes = {s['id'] for s in struct['scopes']}
        for sid in struct['hierarchy']:
            if sid not in scopes: E(f"structure.hierarchy: escopo inexistente {sid}")
        for s in struct['scopes']:
            if s.get('contains') and s['contains'] not in scopes:
                E(f"structure.scopes[{s['id']}].contains: escopo inexistente {s['contains']}")
        for du in struct['durations']:
            for k in ('endsAt', 'resetsAt'):
                v = du.get(k)
                if v and v not in scopes and du.get('kind') != 'usage-limit' and v != 'gift-mark-cleared':
                    E(f"structure.durations[{du['id']}].{k}: escopo inexistente {v}")

    # --- reverie ---
    rev = load(d, 'reverie.json')
    if rev:
        for m in rev['methods']:
            if not isinstance(m.get('dependencyDie'), int) or m['dependencyDie'] < 2:
                E(f"reverie.methods[{m['id']}]: dependencyDie inválido")
        ct = rev['crafting']['test']
        if ct['difficulty'] not in difficulties: E(f"reverie.crafting.test: dificuldade inexistente {ct['difficulty']}")
        for a in ct['approaches']:
            if a not in approaches: E(f"reverie.crafting.test: abordagem inexistente {a}")
        for tgt in rev['effect']['clearsMarks']:
            if tgt not in sysj['sheet']: E(f"reverie.effect.clearsMarks: seção de ficha inexistente {tgt}")

    # --- resources ---
    res = load(d, 'resources.json')
    if res:
        ids = [r['id'] for r in res['resources']]
        if len(ids) != len(set(ids)): E("resources: ids duplicados")
        for r in res['resources']:
            if r['kind'] not in ('permanent', 'consumable'): E(f"resources[{r['id']}]: kind inválido {r['kind']}")

    # --- progression ---
    if prog:
        atypes = {a['id'] for a in prog['advanceTypes']}
        acts = prog['acts']
        if [a['number'] for a in acts] != [1,2,3]: E("progression.acts: numeração deve ser 1,2,3")
        for a in acts:
            for adv in a['advances']:
                if adv not in atypes: E(f"progression.acts[{a['id']}]: tipo de avanço inexistente {adv}")
            if set(a['advances']) != atypes: E(f"progression.acts[{a['id']}]: não cobre todos os tipos de avanço")
        byact = {e['act']: e for e in prog['experienceGift']['byAct']}
        for a in acts:
            e = byact.get(a['number'])
            if not e: E(f"progression.experienceGift: ato {a['number']} ausente"); continue
            if e['keptSuccesses'] != a['keptSuccesses']:
                E(f"progression: keptSuccesses divergente no ato {a['number']} ({a['keptSuccesses']} vs {e['keptSuccesses']})")
            if e['reverieDependencyOn'] != a['reverieDependencyOn']:
                E(f"progression: reverieDependencyOn divergente no ato {a['number']}")
        if mech and prog['acts'][-1]['keptSuccesses'] != mech['test']['keptSuccesses']['max']:
            E("progression/mechanics: keptSuccesses.max não bate com o último ato")
        actnums = {a['number'] for a in acts}
        for ms in prog['milestones']:
            if ms['from'] not in actnums or ms['to'] not in actnums: E(f"progression.milestones[{ms['id']}]: ato inexistente")
        for a in prog['advanceTypes']:
            t = prog['totals'].get({'approach':'approachUpgrades'}.get(a['id'], a['id'] + 's' if a['id']=='gift' else a['id']))
            if t and 'fromAdvances' in t and t['fromAdvances'] != a['max']:
                E(f"progression.totals: fromAdvances de {a['id']} diverge de advanceTypes.max")


def check_dnd(d, sysj, E, W):
    abilities = load(d, 'abilities.json')
    skills = load(d, 'skills.json')
    if abilities is None or skills is None:
        return

    ability_ids = {a['id'] for a in abilities['abilities']}
    skill_by_id = {s['id']: s for s in skills['skills']}

    for s in skills['skills']:
        if s['ability'] not in ability_ids:
            E(f"perícia {s['id']}: habilidade inexistente {s['ability']}")
    if len(skill_by_id) != len(skills['skills']):
        E("skills.json: ids duplicados")

    def cross_skills(items, where):
        for item in items:
            known = skill_by_id.get(item['id'])
            if known is None:
                E(f"{where}: perícia inexistente {item['id']}")
            elif (item['name'], item['ability']) != (known['name'], known['ability']):
                E(f"{where}: perícia {item['id']} diverge de skills.json")

    classes = load(d, 'classes.json')
    if classes:
        ids = [c['id'] for c in classes['classes']]
        if len(ids) != len(set(ids)): E("classes.json: ids duplicados")
        for c in classes['classes']:
            if c['hitDie'] not in (6, 8, 10, 12):
                E(f"classe {c['id']}: dado de vida inválido d{c['hitDie']}")
            for a in c['saving']:
                if a not in ability_ids: E(f"classe {c['id']}: salvaguarda inexistente {a}")
            if len(c['saving']) != 2:
                E(f"classe {c['id']}: {len(c['saving'])} salvaguardas, esperado 2")
            prof = c['proficiency']
            cross_skills(prof['skills'], f"classe {c['id']}")
            if not 1 <= prof['qtd'] <= len(prof['skills']):
                E(f"classe {c['id']}: escolhe {prof['qtd']} de {len(prof['skills'])} perícias")
            if not c['startingEquipment']:
                E(f"classe {c['id']}: sem equipamento inicial")
            if not c['features']:
                E(f"classe {c['id']}: sem características de nível 1")

    races = load(d, 'races.json')
    if races:
        def check_race(r, where):
            for a in r['abilityBonus']:
                if a not in ability_ids: E(f"{where}: bônus em habilidade inexistente {a}")
            if 'speed' in r:
                try:
                    float(r['speed'])
                except (TypeError, ValueError):
                    E(f"{where}: deslocamento não numérico {r.get('speed')!r}")
            if 'size' in r and r['size'] not in SIZES:
                E(f"{where}: tamanho fora do vocabulário {r['size']!r}")

        ids = [r['id'] for r in races['races']]
        if len(ids) != len(set(ids)): E("races.json: ids duplicados")
        for r in races['races']:
            check_race(r, f"raça {r['id']}")
            for sub in r.get('subraces', []):
                check_race(sub, f"sub-raça {sub['id']}")

    backgrounds = load(d, 'backgrounds.json')
    if backgrounds:
        ids = [b['id'] for b in backgrounds['backgrounds']]
        if len(ids) != len(set(ids)): E("backgrounds.json: ids duplicados")
        for b in backgrounds['backgrounds']:
            cross_skills(b['skills'], f"antecedente {b['id']}")
            if not b['feature'].get('name') or not b['feature'].get('desc'):
                E(f"antecedente {b['id']}: característica incompleta")

    equipment = load(d, 'equipment.json')
    if equipment:
        ids = [x['id'] for group in equipment.values() for x in group]
        if len(ids) != len(set(ids)): E("equipment.json: ids duplicados entre os grupos")
        for a in equipment['armor']:
            if a['category'] not in ARMOR_CATEGORIES:
                E(f"armadura {a['id']}: categoria inválida {a['category']!r}")
            if not ({'base', 'dexMod'} <= set(a['ac']) or 'bonus' in a['ac']):
                E(f"armadura {a['id']}: CA malformada {a['ac']}")
        for w in equipment['weapons']:
            if w['category'] not in WEAPON_CATEGORIES:
                E(f"arma {w['id']}: categoria inválida {w['category']!r}")
            if w['damage'] and w['damage']['type'] not in DAMAGE_TYPES:
                E(f"arma {w['id']}: tipo de dano fora do vocabulário {w['damage']['type']!r}")
            for prop in w['properties']:
                if prop not in WEAPON_PROPERTIES:
                    E(f"arma {w['id']}: propriedade fora do vocabulário {prop!r}")


# --- shadowrun ---

SR_ATTRS = ('bod', 'agi', 'rea', 'str', 'wil', 'log', 'int', 'cha', 'ess', 'edg', 'mag', 'res')
SR_OPS = {
    'add': lambda xs: sum(xs),
    'sub': lambda xs: xs[0] - sum(xs[1:]),
    'mul': lambda xs: math.prod(xs),
    'div': lambda xs: xs[0] / xs[1],
    'ceil': lambda xs: math.ceil(xs[0]),
    'floor': lambda xs: math.floor(xs[0]),
    'min': min,
    'max': max,
}
SR_UNARY = {'ceil', 'floor'}
SR_REF = re.compile(r'^(attr\.(' + '|'.join(SR_ATTRS) + r')|rating|grade|karma\.total|quality\.karma'
                    r'|matrix\.dataProcessing|force|netHits)$')
SR_TARGETS = {
    'attr.max', 'skill.max', 'limit', 'monitor.overflow', 'wound.ignoredBoxes', 'wound.boxesPerPenalty',
    'reputation.notoriety', 'essence.cyberwareLoss', 'lifestyle.cost', 'language.native',
    'matrix.biofeedbackFilter', 'progression.trainingTime', 'reach', 'armor',
    'attr', 'initiative.dice', 'skill.rating', 'weapon.accuracy', 'weapon.damage',
}
# O que cada alvo seleciona com "of".
SR_SELECTS = {'attr': 'attribute', 'attr.max': 'attribute', 'skill.max': 'skill', 'skill.rating': 'skill',
              'weapon.accuracy': 'skill', 'weapon.damage': 'skill', 'limit': 'limit'}
SR_LIMITS = ('physical', 'mental', 'social')
SR_SKILL_CATEGORIES = {'combat', 'physical', 'social', 'magical', 'resonance', 'technical', 'vehicle'}

# Personagens de exemplo do livro: atributos das p. 67 e 70, resultados da p. 102.
SR_EXAMPLES = [
    ('Clara', {'bod': 3, 'agi': 6, 'rea': 3, 'str': 2, 'wil': 4, 'log': 3, 'int': 4, 'cha': 6, 'ess': 6},
     {'initiative': 7, 'physical': 4, 'mental': 5, 'social': 8, 'physicalBoxes': 10, 'stunBoxes': 10,
      'overflow': 3, 'contacts': 18, 'knowledge': 14}),
    # O livro calcula o limite Social do Beto com Essência 6, antes das ampliações.
    ('Beto', {'bod': 9, 'agi': 4, 'rea': 3, 'str': 11, 'wil': 4, 'log': 3, 'int': 3, 'cha': 3, 'ess': 6},
     {'initiative': 6, 'physical': 12, 'mental': 5, 'social': 6, 'physicalBoxes': 13, 'stunBoxes': 10,
      'overflow': 9, 'contacts': 9, 'knowledge': 12}),
    # A Persona Viva e a Iniciativa da Matriz do exemplo não batem com os
    # atributos do Jefferson (Ataque 5 com Carisma 3), então ficam de fora.
    ('Jefferson', {'bod': 3, 'agi': 2, 'rea': 2, 'str': 3, 'wil': 3, 'log': 4, 'int': 4, 'cha': 3, 'ess': 6},
     {'initiative': 6, 'physical': 4, 'mental': 5, 'social': 5, 'physicalBoxes': 10, 'stunBoxes': 10,
      'overflow': 3, 'contacts': 9, 'knowledge': 16}),
]


def sr_eval(expr, env):
    if isinstance(expr, (int, float)) and not isinstance(expr, bool): return expr
    if 'ref' in expr: return env[expr['ref']]
    return SR_OPS[expr['op']]([sr_eval(a, env) for a in expr['of']])


def is_expr(o):
    return isinstance(o, dict) and ('op' in o or 'ref' in o)


def sr_check_expr(expr, where, E):
    if isinstance(expr, (int, float)) and not isinstance(expr, bool): return
    if not is_expr(expr): E(f"{where}: fórmula malformada {expr!r}"); return
    if 'ref' in expr:
        if set(expr) != {'ref'} or not SR_REF.match(expr['ref']): E(f"{where}: referência inválida {expr!r}")
        return
    if set(expr) != {'op', 'of'} or expr['op'] not in SR_OPS or not isinstance(expr['of'], list):
        E(f"{where}: operação inválida {expr!r}"); return
    if expr['op'] in SR_UNARY and len(expr['of']) != 1: E(f"{where}: {expr['op']} recebe um operando")
    if expr['op'] in ('sub', 'div') and len(expr['of']) != 2: E(f"{where}: {expr['op']} recebe dois operandos")
    for i, a in enumerate(expr['of']): sr_check_expr(a, f"{where}.{expr['op']}[{i}]", E)


def sr_walk_exprs(o, path=""):
    if is_expr(o): yield path, o; return
    if isinstance(o, dict):
        for k, v in o.items(): yield from sr_walk_exprs(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from sr_walk_exprs(v, f"{path}[{i}]")


def sr_check_modifier(m, where, E, skill_ids, parameter=None):
    """parameter é o parâmetro da entrada dona do modificador, para "of": "parameter"."""
    ops = [k for k in ('add', 'mul', 'set') if k in m]
    if len(ops) != 1: E(f"{where}: modificador precisa de exatamente um entre add/mul/set"); return
    sr_check_expr(m[ops[0]], where, E)
    target, sel = m.get('target'), m.get('of')
    if target not in SR_TARGETS: E(f"{where}: alvo fora do vocabulário {target!r}")
    kind = SR_SELECTS.get(target)
    valid = {'attribute': SR_ATTRS, 'limit': SR_LIMITS, 'skill': skill_ids}.get(kind, ())
    if sel is None: pass
    elif sel == 'parameter':
        if not parameter: E(f"{where}: 'of': 'parameter' sem parâmetro na entrada")
        elif parameter['kind'] != kind: E(f"{where}: parâmetro {parameter['kind']} incompatível com {target}")
    elif isinstance(sel, str):
        if sel not in valid: E(f"{where}: {kind or target} inexistente {sel}")
    elif isinstance(sel, dict):
        if sel.get('choose') != kind: E(f"{where}: escolha {sel.get('choose')!r} incompatível com {target}")
        for a in sel.get('except', []) + sel.get('only', []):
            if a not in valid: E(f"{where}: {kind} inexistente em except/only: {a}")
    else:
        E(f"{where}: seletor 'of' inválido {sel!r}")
    if 'times' in m: sr_check_expr(m['times'], f"{where}.times", E)


def sr_check_parameter(param, where, E, skill_ids, skill_categories):
    kind = param.get('kind')
    valid = {'attribute': SR_ATTRS, 'limit': SR_LIMITS, 'skill': skill_ids}.get(kind)
    if valid is None: E(f"{where}: parâmetro de tipo desconhecido {kind!r}"); return
    for o in param.get('options', []) + param.get('except', []):
        if o not in valid: E(f"{where}: opção de parâmetro inexistente {o}")
    for c in param.get('categories', []):
        if c not in skill_categories: E(f"{where}: categoria de perícia inexistente {c}")


def check_shadowrun(d, sysj, E, W):
    attributes = load(d, 'attributes.json')
    metatypes = load(d, 'metatypes.json')
    priorities = load(d, 'priorities.json')
    awakening = load(d, 'awakening.json')
    skills = load(d, 'skills.json')
    qualities = load(d, 'qualities.json')
    mech = load(d, 'mechanics.json')
    lifestyles = load(d, 'lifestyles.json')

    # --- fórmulas, em qualquer catálogo ---
    for fname in sysj['catalogs']:
        obj = load(d, fname)
        for path, expr in sr_walk_exprs(obj or {}):
            sr_check_expr(expr, f"{fname}{path}", E)

    if [a['id'] for a in attributes['attributes']] != list(SR_ATTRS):
        E("attributes.json: ids ou ordem divergem do vocabulário")

    meta_ids = set()
    for m in metatypes['metatypes']:
        meta_ids.add(m['id'])
        attrs = m['attributes']
        if set(attrs) != set(SR_ATTRS) - {'mag', 'res'}:
            E(f"metatipo {m['id']}: atributos devem ser os físicos, mentais, Trunfo e Essência")
        for a, r in attrs.items():
            if a == 'ess':
                if r != {'start': 6}: E(f"metatipo {m['id']}: Essência deve começar em 6")
            elif not 1 <= r['min'] <= r['max']: E(f"metatipo {m['id']}: faixa inválida de {a} {r}")
        for t in m['traits']:
            for i, mod in enumerate(t.get('modifiers', [])):
                sr_check_modifier(mod, f"metatipo {m['id']} traço {t['id']}[{i}]", E, set())

    skill_ids = {s['id'] for s in skills['skills']}
    group_ids = {g['id'] for g in skills['groups']}
    if len(skill_ids) != len(skills['skills']): E("skills.json: ids duplicados")
    for s in skills['skills']:
        if s['attribute'] not in SR_ATTRS: E(f"perícia {s['id']}: atributo inexistente {s['attribute']}")
        if s['category'] not in SR_SKILL_CATEGORIES: E(f"perícia {s['id']}: categoria inválida {s['category']}")
        if s['group'] is not None and s['group'] not in group_ids: E(f"perícia {s['id']}: grupo inexistente {s['group']}")
        if s['restricted'] != (s['attribute'] in ('mag', 'res')): E(f"perícia {s['id']}: restricted incoerente com o atributo")
        if not isinstance(s['default'], bool): E(f"perícia {s['id']}: default deve ser booleano")
    for g in skills['groups']:
        members = {s['id'] for s in skills['skills'] if s['group'] == g['id']}
        if set(g['skills']) != members: E(f"grupo {g['id']}: membros divergem do campo group das perícias")
    for c in skills['knowledge']['categories']:
        if c['attribute'] not in SR_ATTRS: E(f"conhecimento {c['id']}: atributo inexistente")

    awakening_by_id = {a['id']: a for a in awakening['awakenings']}
    for a in awakening['awakenings']:
        if a['attribute'] not in ('mag', 'res'): E(f"despertar {a['id']}: atributo deve ser mag ou res")
        if a.get('magicSkillGroups', 'none') not in ('all', 'one', 'none'):
            E(f"despertar {a['id']}: magicSkillGroups inválido")

    rows = priorities['rows']
    if [r['priority'] for r in rows] != list('ABCDE'): E("priorities.json: linhas devem ser A–E, nessa ordem")
    columns = [c['id'] for c in priorities['columns']]
    for r in rows:
        for c in columns:
            if c not in r: E(f"prioridade {r['priority']}: coluna ausente {c}")
        for m in r['metatype']:
            if m['metatype'] not in meta_ids: E(f"prioridade {r['priority']}: metatipo inexistente {m['metatype']}")
            if m['specialPoints'] < 0: E(f"prioridade {r['priority']}: pontos especiais negativos")
        for g in r['magic']:
            aw = awakening_by_id.get(g['awakening'])
            if aw is None: E(f"prioridade {r['priority']}: despertar inexistente {g['awakening']}"); continue
            if g['attribute']['id'] != aw['attribute']:
                E(f"prioridade {r['priority']}: {g['awakening']} recebe {g['attribute']['id']}, despertar usa {aw['attribute']}")
            for key in ('skills', 'skillGroups'):
                src = g.get(key, {}).get('from', {})
                for gid in src.get('groups', []):
                    if gid not in group_ids: E(f"prioridade {r['priority']}: grupo inexistente {gid}")
                if src.get('attribute') and src['attribute'] not in SR_ATTRS:
                    E(f"prioridade {r['priority']}: atributo inexistente {src['attribute']}")
    for c in ('attributes', 'resources'):
        values = [r[c] for r in rows]
        if values != sorted(values, reverse=True) or len(set(values)) != len(values):
            E(f"priorities.json: coluna {c} deve decrescer de A para E")
    if {m['metatype'] for m in rows[0]['metatype']} != meta_ids: E("prioridade A deve oferecer todos os metatipos")

    qs = qualities['qualities']
    if len({q['id'] for q in qs}) != len(qs): E("qualities.json: ids duplicados")
    kinds = [q['kind'] for q in qs]
    if (kinds.count('positive'), kinds.count('negative')) != (31, 28):
        E(f"qualities.json: esperado 31 positivas e 28 negativas, há {kinds.count('positive')}/{kinds.count('negative')}")
    for q in qs:
        k = q['karma']
        if isinstance(k, dict) and 'perLevel' in k and not q.get('levels', {}).get('max'):
            E(f"qualidade {q['id']}: custo por nível sem levels.max")
        if not isinstance(k, int) and not (isinstance(k, dict) and len(k) == 1 and set(k) <= {'perLevel', 'options', 'sum'}):
            E(f"qualidade {q['id']}: forma de custo inválida {k!r}")
        opts = k.get('options', []) if isinstance(k, dict) else []
        if len({o['id'] for o in opts}) != len(opts): E(f"qualidade {q['id']}: opções com id duplicado")
        mods = q.get('modifiers', []) + [m for o in opts for m in o.get('modifiers', [])]
        for i, m in enumerate(mods):
            sr_check_modifier(m, f"qualidade {q['id']}[{i}]", E, skill_ids)
            if m.get('target') == 'reputation.notoriety' and (m['add'] < 0) != (q['kind'] == 'positive'):
                E(f"qualidade {q['id']}: sinal da notoriedade incoerente com o tipo")
        if not q.get('desc'): E(f"qualidade {q['id']}: desc vazia")

    powers = load(d, 'adept-powers.json')
    if powers:
        if len({p['id'] for p in powers['powers']}) != len(powers['powers']): E("adept-powers.json: ids duplicados")
        activations = {a['id'] for a in powers['activations']}
        for p in powers['powers']:
            where = f"poder {p['id']}"
            if p.get('parameter'): sr_check_parameter(p['parameter'], where, E, skill_ids, SR_SKILL_CATEGORIES)
            if p.get('activation') and p['activation'] not in activations: E(f"{where}: ativação inexistente")
            for i, m in enumerate(p.get('modifiers', [])):
                sr_check_modifier(m, f"{where}[{i}]", E, skill_ids, p.get('parameter'))

    mentors = load(d, 'mentors.json')
    if mentors and powers:
        power_by_id = {p['id']: p for p in powers['powers']}
        quality_by_id = {q['id']: q for q in qualities['qualities']}
        for m in mentors['mentors']:
            where = f"mentor {m['id']}"
            for g in m['adeptGrants']:
                pw = power_by_id.get(g['power'])
                if pw is None: E(f"{where}: poder inexistente {g['power']}"); continue
                per_level = isinstance(pw['powerPoints'], dict) and ('perLevel' in pw['powerPoints'] or 'byLevel' in pw['powerPoints'])
                if ('levels' in g) != per_level: E(f"{where}: levels só vale para poderes com custo por nível ({g['power']})")
                sel = g.get('parameter')
                if sel is None: continue
                if not pw.get('parameter'): E(f"{where}: {g['power']} não tem parâmetro para restringir"); continue
                if isinstance(sel, str):
                    if sel not in pw['parameter'].get('options', []): E(f"{where}: {sel} não é opção de {g['power']}")
                else:
                    for gid in sel.get('groups', []):
                        if gid not in group_ids: E(f"{where}: grupo inexistente {gid}")
                    for c in sel.get('categories', []) + sel.get('exceptCategories', []):
                        if c not in SR_SKILL_CATEGORIES: E(f"{where}: categoria inexistente {c}")
            dq = m.get('disadvantageQuality')
            if dq:
                q = quality_by_id.get(dq['quality'])
                if q is None: E(f"{where}: qualidade inexistente {dq['quality']}"); continue
                factors = {f['id']: {o['id'] for o in f['options']} for f in q['karma'].get('sum', [])} \
                    if isinstance(q['karma'], dict) else {}
                for fid, oid in dq.get('options', {}).items():
                    if oid not in factors.get(fid, set()): E(f"{where}: opção {fid}={oid} inexistente em {q['id']}")

    for l in lifestyles['identities']:
        if l['availability']['legality'] not in mech['legality']:
            E(f"identidade {l['id']}: legalidade fora do vocabulário")
    costs = [l['cost'] for l in lifestyles['lifestyles'] if 'cost' in l]
    if costs != sorted(costs): E("lifestyles.json: estilos de vida devem vir em ordem crescente de custo")

    # --- exemplos do livro ---
    derived = mech['derived']
    for name, attrs, want in SR_EXAMPLES:
        env = {f'attr.{a}': v for a, v in attrs.items()}
        got = {
            'initiative': sr_eval(derived['initiative']['physical']['base'], env),
            'physical': sr_eval(derived['limits']['physical']['value'], env),
            'mental': sr_eval(derived['limits']['mental']['value'], env),
            'social': sr_eval(derived['limits']['social']['value'], env),
            'physicalBoxes': sr_eval(derived['monitors']['physical']['boxes'], env),
            'stunBoxes': sr_eval(derived['monitors']['stun']['boxes'], env),
            'overflow': sr_eval(derived['monitors']['overflow']['boxes'], env),
            'contacts': sr_eval(mech['creation']['contacts']['karma'], env),
            'knowledge': sr_eval(mech['creation']['skills']['knowledgePoints'], env),
        }
        for k, v in want.items():
            if got[k] != v: E(f"exemplo {name}: {k} dá {got[k]}, o livro diz {v}")

    # Beto tem Desejo de Viver 1: Excesso 9 (10), p. 102.
    wtl = next(q for q in qs if q['id'] == 'will-to-live')['modifiers'][0]
    if 9 + sr_eval(wtl['add'], {'rating': 1}) != 10: E("exemplo Beto: Desejo de Viver não leva o Excesso a 10")

    # Compras dos exemplos, p. 97: SIN falso 4 = 10.000¥, licença 3 = 600¥;
    # Estilo de Vida Baixo por 3 meses para troll = 12.000¥.
    ids = {i['id']: i for i in lifestyles['identities']}
    for iid, rating, price in (('fake-sin', 4, 10000), ('fake-sin', 3, 7500), ('fake-license', 4, 800),
                               ('fake-license', 3, 600)):
        if sr_eval(ids[iid]['cost'], {'rating': rating}) != price: E(f"{iid} nível {rating}: preço diverge da p. 97")
    low = next(l for l in lifestyles['lifestyles'] if l['id'] == 'low')['cost']
    troll = next(m for m in metatypes['metatypes'] if m['id'] == 'troll')
    mult = next(mod['mul'] for t in troll['traits'] for mod in t.get('modifiers', []) if mod['target'] == 'lifestyle.cost')
    if low * mult * 3 != 12000: E("exemplo Beto: Estilo de Vida Baixo de troll por 3 meses deveria custar 12.000¥")

    # Progressão, p. 106: Reação 2→3 custa 15; perícia 1→2 custa 4; 5→6 custa 12.
    prog = mech['progression']['costs']
    for key, rating, cost in (('attribute', 3, 15), ('activeSkill', 2, 4), ('activeSkill', 6, 12)):
        if sr_eval(prog[key], {'rating': rating}) != cost: E(f"progressão {key} nível {rating}: esperado {cost}")


def check(d):
    err, warn = [], []
    E, W = err.append, warn.append

    sysj = load(d, 'system.json')
    if sysj is None: return ["system.json ausente"], []

    for f in sysj['catalogs']:
        if not (d / f).exists(): E(f"catálogo declarado e ausente: {f}")

    checker = {'vileborn': check_vileborn, 'dnd': check_dnd, 'shadowrun': check_shadowrun}.get(sysj['id'])
    if checker:
        checker(d, sysj, E, W)

    # --- marca d'água dos PDFs: nome e e-mail do licenciado não podem vazar ---
    for fname in sysj['catalogs'] + ['system.json']:
        p = d / fname
        if p.exists() and ('Licenciado' in p.read_text() or '@' in p.read_text()):
            E(f"{fname}: contém marca d'água do PDF ('Licenciado' ou '@')")

    # --- ponteiros entre arquivos (qualquer string no formato arquivo.json#caminho) ---
    for fname in sysj['catalogs'] + ['system.json']:
        obj = load(d, fname)
        if obj is None: continue
        for path, val in walk_strings(obj):
            if POINTER.match(val) and resolve(d, val) is None:
                E(f"{fname}{path}: ponteiro não resolve -> {val}")

    return err, warn

rc = 0
for arg in (sys.argv[1:] or sorted(str(p) for p in ROOT.glob('*/*') if (p / 'system.json').is_file())):
    d = pathlib.Path(arg)
    err, warn = check(d)
    print(f"[{d}]")
    for w in warn: print(f"  aviso: {w}")
    for e in err: print(f"  ERRO : {e}")
    if not err: print(f"  ok ({len(warn)} aviso(s))")
    rc |= bool(err)
sys.exit(rc)
