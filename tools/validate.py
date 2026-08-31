#!/usr/bin/env python3
"""Valida os catálogos de um sistema. Sem dependências: python3 validate.py [dir...]"""
import json, re, sys, pathlib

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


def check(d):
    err, warn = [], []
    E, W = err.append, warn.append

    sysj = load(d, 'system.json')
    if sysj is None: return ["system.json ausente"], []

    # Catálogo servido do Mongo pode não ter arquivo em disco; só as checagens
    # que dependem de arquivo ficam condicionadas à origem.
    on_disk = sysj.get('catalogSource', 'embed') == 'embed'

    if on_disk:
        for f in sysj['catalogs']:
            if not (d / f).exists(): E(f"catálogo declarado e ausente: {f}")

    checker = {'vileborn': check_vileborn, 'dnd': check_dnd}.get(sysj['id'])
    if checker:
        checker(d, sysj, E, W)

    # --- ponteiros entre arquivos (qualquer string no formato arquivo.json#caminho) ---
    for fname in (sysj['catalogs'] + ['system.json']) if on_disk else []:
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
