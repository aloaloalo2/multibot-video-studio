// Read-only static dependencies. Reuse Playwright's pinned Babel parser; never execute scene code.
const fs = require('fs');
const path = require('path');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let babel;
for (let folder of [input.root, __dirname]) {
  while (folder && !babel) {
    for (const suffix of ['node_modules/playwright/lib/transform/babelBundle.js', 'razgon-2d-studio/node_modules/playwright/lib/transform/babelBundle.js']) {
      try { babel = require(path.join(folder, suffix)); break; } catch {}
    }
    const parent = path.dirname(folder); if (parent === folder) break; folder = parent;
  }
}
if (!babel) throw new Error('Static parser unavailable');
const flatten = value => typeof value === 'string' ? [value] : Array.isArray(value) ? value.flatMap(flatten) : value && typeof value === 'object' ? Object.values(value).flatMap(flatten) : [];
function arrayValues(p, column, seen) {
  if (p.isIdentifier()) {
    const b = p.scope.getBinding(p.node.name);
    if (!b?.constant || !b.path.isVariableDeclarator()) return null;
    p = b.path.get('init');
  }
  if (!p.isArrayExpression()) {
    const result = p.evaluate();
    return result.confident && Array.isArray(result.value) ? result.value.flatMap(row => flatten(column == null ? row : row?.[column])) : null;
  }
  const parts = p.get('elements').map(row => column == null ? values(row, seen) : row.isArrayExpression() ? values(row.get(`elements.${column}`), seen) : null);
  return parts.every(v => v !== null) ? parts.flat() : null;
}
function values(p, seen = new Set()) {
  if (!p?.node || seen.has(p.node)) return null;
  seen = new Set(seen).add(p.node);
  const result = p.evaluate();
  if (result.confident) return flatten(result.value);
  if (p.isConditionalExpression() || p.isLogicalExpression()) {
    const a = values(p.get(p.isConditionalExpression() ? 'consequent' : 'left'), seen);
    const b = values(p.get(p.isConditionalExpression() ? 'alternate' : 'right'), seen);
    return a && b ? [...a, ...b] : null;
  }
  if (p.isTemplateLiteral()) return [p.node.quasis.map(q => q.value.cooked).join('*')];
  if (p.isBinaryExpression({operator:'+'})) {
    const a = values(p.get('left'), seen), b = values(p.get('right'), seen);
    return a?.length || b?.length ? (a || ['*']).flatMap(x => (b || ['*']).map(y => x + y)) : null;
  }
  if (p.isMemberExpression()) return values(p.get('object'), seen);
  if (!p.isIdentifier()) return null;
  const binding = p.scope.getBinding(p.node.name);
  if (!binding?.constant) return null;
  if (binding.kind === 'param') {
    const fn = binding.path.findParent(x => x.isFunction()), call = fn?.parentPath;
    if (!call?.isCallExpression() || !['forEach','map'].includes(call.node.callee.property?.name)) return null;
    const pattern = fn.node.params[0];
    const column = pattern.type === 'ArrayPattern' ? pattern.elements.findIndex(n => n?.name === p.node.name) : null;
    if (column === -1 || (column == null && pattern.name !== p.node.name)) return null;
    return arrayValues(call.get('callee.object'), column, seen);
  }
  if (!binding.path.isVariableDeclarator()) return null;
  const declaration = binding.path;
  const loop = declaration.parentPath.parentPath;
  if (loop.isForOfStatement()) {
    if (declaration.get('id').isIdentifier()) return arrayValues(loop.get('right'), null, seen);
    const index = declaration.node.id.elements.findIndex(n => n?.name === p.node.name);
    return index < 0 ? null : arrayValues(loop.get('right'), index, seen);
  }
  return values(declaration.get('init'), seen);
}
function canvas(p, seen = new Set()) {
  if (!p?.node) return false;
  if (seen.has(p.node)) return true; // A closed cache cycle cannot introduce an external image.
  seen = new Set(seen).add(p.node);
  if (p.isIdentifier()) {
    const b = p.scope.getBinding(p.node.name);
    if (!b?.path.isVariableDeclarator()) return false;
    return canvas(b.path.get('init'), seen) && b.constantViolations.every(v => v.isAssignmentExpression() && canvas(v.get('right'), seen));
  }
  if (p.isConditionalExpression()) return canvas(p.get('consequent'), seen) && canvas(p.get('alternate'), seen);
  if (p.isNewExpression() && p.node.callee.name === 'OffscreenCanvas' && !p.scope.getBinding('OffscreenCanvas')) return true;
  if (!p.isCallExpression()) return false;
  const c = p.node.callee;
  if (c.type === 'MemberExpression' && c.object.name === 'document' && c.property.name === 'createElement' && !p.scope.getBinding('document')) return p.node.arguments[0]?.value === 'canvas';
  if (c.type === 'MemberExpression' && c.property.name === 'get' && c.object.type === 'Identifier') {
    const b = p.scope.getBinding(c.object.name), init = b?.path.isVariableDeclarator() ? b.path.get('init') : null;
    if (!b?.constant || !init?.isNewExpression() || init.node.callee.name !== 'Map' || init.node.arguments.length || init.scope.getBinding('Map')) return false;
    return b.referencePaths.every(ref => {
      const member = ref.parentPath, call = member.parentPath;
      if (!member.isMemberExpression() || member.node.object !== ref.node || !call.isCallExpression() || call.node.callee !== member.node) return false;
      if (member.node.property.name === 'set') return canvas(call.get('arguments.1'), seen);
      return ['get','has','clear','delete'].includes(member.node.property.name);
    });
  }
  if (c.type !== 'Identifier') return false;
  const fn = p.scope.getBinding(c.name)?.path;
  if (!fn?.isFunctionDeclaration()) return false;
  const returns = [];
  fn.traverse({ReturnStatement(ret) { if (ret.getFunctionParent() === fn) returns.push(ret.get('argument')); }});
  return returns.length > 0 && returns.every(ret => canvas(ret, seen));
}
const modules = input.files.map(file => {
  try { return {...file, ast:babel.babelParse(file.source, file.path, true)}; }
  catch { return {...file, ast:null}; }
});
function pureTopLevel(p) {
  if (p.isImportDeclaration() || p.isExportAllDeclaration() || p.isFunctionDeclaration() || p.isEmptyStatement()) return true;
  if (p.isExportNamedDeclaration() || p.isExportDefaultDeclaration()) return !p.node.declaration || pureTopLevel(p.get('declaration'));
  if (p.isVariableDeclaration()) return p.get('declarations').every(d => {
    const init = d.get('init');
    return !init.node || init.isPure() || init.evaluate().confident ||
      (init.isNewExpression() && ['Map','Set'].includes(init.node.callee.name) && !init.scope.getBinding(init.node.callee.name) && !init.node.arguments.length);
  });
  return p.isExpressionStatement() && p.get('expression').isPure();
}
const apis = new Map([['pic', new Set([1])], ['picTint', new Set([1])], ['fetch',new Set([0])]]);
const fetchers = new Set(['fetch']);
const forwarded = new Set();
// Follow ordinary wrappers such as grounded(g, name, ...), without treating their formal name as an unknown prop.
for (let pass = 0; pass < 8; pass++) {
  let changed = false;
  for (const module of modules) if (module.ast) babel.traverse(module.ast, {
  'ImportSpecifier|ExportSpecifier'(p) {
    const from = p.node.imported?.name || p.node.local?.name, to = p.node.imported ? p.node.local?.name : p.node.exported?.name;
    if (from !== to && apis.has(from) && !apis.has(to)) { apis.set(to,new Set(apis.get(from))); if (fetchers.has(from)) fetchers.add(to); changed = true; }
  },
  VariableDeclarator(p) {
    const from = p.node.init?.name, to = p.node.id.name;
    if (to && apis.has(from) && !apis.has(to)) { apis.set(to,new Set(apis.get(from))); if (fetchers.has(from)) fetchers.add(to); changed = true; }
  },
  ObjectProperty(p) {
    const from = p.node.key.name || p.node.key.value, to = p.node.value.name;
    if (p.parentPath.isObjectPattern() && to && apis.has(from) && !apis.has(to)) { apis.set(to,new Set(apis.get(from))); if (fetchers.has(from)) fetchers.add(to); changed = true; }
  },
  'CallExpression|OptionalCallExpression'(p) {
    const name = p.node.callee.name || p.node.callee.property?.name || p.node.callee.property?.value;
    const indexes = apis.get(name); if (!indexes) return;
    for (const index of indexes) {
      const arg = p.get(`arguments.${index}`); if (!arg?.isIdentifier()) continue;
      const binding = arg.scope.getBinding(arg.node.name); if (binding?.kind !== 'param') continue;
      const fn = binding.path.findParent(x => x.isFunction());
      const name = fn?.node.id?.name || (fn?.parentPath.isVariableDeclarator() ? fn.parentPath.node.id.name : null);
      const at = fn?.node.params.findIndex(x => x.name === arg.node.name);
      if (!name || at < 0) continue;
      if (!apis.has(name)) apis.set(name, new Set());
      if (!apis.get(name).has(at)) { apis.get(name).add(at); changed = true; }
      if (fetchers.has(p.node.callee.name || p.node.callee.property?.name || p.node.callee.property?.value)) fetchers.add(name);
      forwarded.add(p.node);
    }
  }});
  if (!changed) break;
}
// Scene modules are loaded for registration. A named helper that nobody imports
// or calls cannot select a PNG. Keep the conservative path for open module graphs.
const imported = new Set();
let closed = modules.every(m => m.ast);
for (const module of modules) if (module.ast) babel.traverse(module.ast, {
  ImportDeclaration(p) {
    for (const spec of p.node.specifiers) {
      if (spec.type === 'ImportNamespaceSpecifier' && !p.node.source.value.startsWith('/engine/')) closed = false;
      if (spec.imported) imported.add(spec.imported.name || spec.imported.value);
    }
  },
  ExportAllDeclaration() { closed = false; },
  ExportSpecifier(p) { imported.add(p.node.local.name || p.node.local.value); },
  enter(p) {
    if (p.node.type === 'ImportExpression' || p.node.type === 'Import' || p.node.type === 'ExportNamespaceSpecifier') closed = false;
  },
  ReferencedIdentifier(p) { if (['eval','Function'].includes(p.node.name)) closed = false; }
});
const output = {};
for (const module of modules) {
  const names = new Set(), takes = new Set(), patterns = new Set();
  let dynamic = !module.ast;
  let global = !module.ast;
  const loader = path.basename(module.path) === 'assets.js' && module.source.includes("fetch('/project/assets/index.json'") && module.source.includes('/project/assets/${name}.png');
  if (module.ast) babel.traverse(module.ast, {
    Program(p) { global = !p.get('body').every(pureTopLevel); },
    FunctionDeclaration(p) {
      const name = p.node.id?.name;
      if (!closed || !name || !p.parentPath.isExportNamedDeclaration() || imported.has(name)) return;
      const binding = p.parentPath.scope.getBinding(name);
      // Babel includes the export declaration itself in referencePaths.
      if (binding?.constant && binding.referencePaths.every(ref => ref.node === p.parentPath.node)) p.skip();
    },
    StringLiteral(p) { names.add(p.node.value); },
    ReferencedIdentifier(p) {
      if (!apis.has(p.node.name)) return;
      const parent = p.parentPath;
      if ((parent.isCallExpression() || parent.isOptionalCallExpression()) && parent.node.callee === p.node) return;
      if (parent.isExportSpecifier() || parent.isImportSpecifier()) return;
      if (parent.isVariableDeclarator() && parent.node.init === p.node && apis.has(parent.node.id.name)) return;
      dynamic = true; // A callback/escaped drawing function can choose arbitrary props.
    },
    'CallExpression|OptionalCallExpression'(p) {
      const name = p.node.callee.name || p.node.callee.property?.name || p.node.callee.property?.value;
      if (name === 'take' || name === 'registerShot') for (const value of values(p.get('arguments.0')) || []) takes.add(value);
      const indexes = apis.get(name);
      if (indexes && !forwarded.has(p.node)) for (const index of indexes) {
        const found = values(p.get(`arguments.${index}`));
        if (found === null) dynamic = true; else found.forEach(x => (x.includes('*') ? patterns : names).add(x));
      }
      if (!loader && p.node.callee.type === 'MemberExpression' && name === 'drawImage' && !canvas(p.get('arguments.0'))) dynamic = true;
      if (p.node.callee.type.endsWith('MemberExpression') && p.node.callee.computed && !p.node.callee.property.value) dynamic = true;
      if (fetchers.has(name) && !loader) {
        for (const index of indexes || [0]) {
          const found = values(p.get(`arguments.${index}`));
          if (found === null || found.some(x => x.includes('assets/index.json'))) dynamic = true;
        }
      }
    },
    AssignmentExpression(p) {
      const left = p.node.left;
      if (!loader && left.type === 'MemberExpression' && ['src','backgroundImage'].includes(left.property.name)) {
        const found = values(p.get('right'));
        if (found === null) dynamic = true; else found.forEach(x => (x.includes('*') ? patterns : names).add(x));
      }
    }
  });
  output[module.path] = {names:[...names], patterns:[...patterns], takes:[...takes], dynamic, global};
}
process.stdout.write(JSON.stringify(output));
