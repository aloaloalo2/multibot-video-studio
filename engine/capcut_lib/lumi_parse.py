"""Parse CapCut Lumi transition packages: LumiExportData.lua + main.scene graph."""
import re, os, glob, json, sys

def lua_to_py(src):
    # tokenize lua table literal subset
    toks = re.findall(r"--[^\n]*|\[\[.*?\]\]|'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\"|Amaz\.\w+\(|[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?|[A-Za-z_][\w\.]*|[{}\[\]=,();]", src, re.S)
    toks = [t for t in toks if not t.startswith('--')]
    pos = 0
    def peek(): return toks[pos] if pos < len(toks) else None
    def nxt():
        nonlocal pos; t = toks[pos]; pos += 1; return t
    def value():
        t = nxt()
        if t == '{': return table()
        if t.startswith('Amaz.'):
            args = []
            while peek() != ')':
                if peek() == ',': nxt(); continue
                args.append(value())
            nxt(); return args
        if t[0] in "'\"": return t[1:-1]
        if t == 'true': return True
        if t == 'false': return False
        if t == 'nil': return None
        try: return float(t)
        except ValueError: return ('ref', t)
    def table():
        arr = []; d = {}
        while True:
            t = peek()
            if t == '}': nxt(); break
            if t == ',' or t == ';': nxt(); continue
            if t == '[':
                nxt(); k = value(); assert nxt() == ']'; assert nxt() == '='; d[k] = value(); continue
            if re.match(r'[A-Za-z_]\w*$', t or '') and toks[pos+1] == '=':
                nxt(); nxt(); d[t] = value(); continue
            arr.append(value())
        if d and arr:
            for i, v in enumerate(arr): d[i] = v
            return d
        return d if d else arr
    out = {}
    while pos < len(toks):
        t = nxt()
        if t == 'local' or t == 'return': continue
        if t.startswith('data.') : 
            nxt(); value(); continue
        if re.match(r'[A-Za-z_]\w*$', t) and peek() == '=':
            nxt(); out[t] = value()
    return out

TEXKEY = re.compile(r'^([A-Za-z]*Tex[A-Za-z0-9]*?)(?:[^A-Za-z0-9].*|EJ.*)?$')
def parse_scene(path):
    data = open(path, 'rb').read()
    strs = [s.decode('utf-8', 'ignore') for s in re.findall(rb'[\x20-\x7e]{3,}', data)]
    nodes = []; cur = None
    i = 0
    while i < len(strs):
        s = strs[i]
        m = re.match(r'^(Lumi[A-Za-z0-9_]+_\d+-(?:trs-blend|trs|blend|effect\d+|[a-z]+\d*))\.?$', s)
        if m:
            cur = {'name': m.group(1), 'tex': {}, 'str': {}}; nodes.append(cur); i += 1; continue
        if cur is not None:
            mk = re.match(r'^([A-Za-z0-9]*Tex[A-Za-z0-9]*?)(EJ|E|\W|$)', s)
            if mk and i + 1 < len(strs) and (strs[i+1].startswith('share://') or strs[i+1].startswith('rt/') or '/' in strs[i+1]):
                cur['tex'][mk.group(1)] = strs[i+1]; i += 2; continue
            mk = re.match(r'^(layerType|blendMode|matteMode)', s)
            if mk and i + 1 < len(strs):
                cur['str'][mk.group(1)] = strs[i+1]; i += 2; continue
        i += 1
    return nodes

def load(pkgdir):
    af = glob.glob(os.path.join(pkgdir, '**/AmazingFeature'), recursive=True)[0]
    lua = open(os.path.join(af, 'lua/LumiFamily/LumiExportData.lua'), encoding='utf-8').read()
    d = lua_to_py(lua)
    d['scene'] = parse_scene(os.path.join(af, 'main.scene'))
    d['root'] = af
    return d

if __name__ == '__main__':
    for p in sorted(glob.glob(sys.argv[1] + '/*/')):
        d = load(p)
        print('==', os.path.basename(p[:-1]), d['ae_compDurations'], d['ae_transitionInputIndex'])
        for n in d['scene']:
            print('   ', n['name'], n['tex'], n['str'])
