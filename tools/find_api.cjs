// 在 app.asar 里流式搜索，把命中处前后一大段打出来。用法：
//   node find_api.cjs "关键词1" "关键词2" ...
// asar 路径：优先 $DSH_ASAR，否则按 %LOCALAPPDATA% 推（不写死任何用户名）。
const fs = require('node:fs');
const path = require('node:path');

const ASAR =
  process.env.DSH_ASAR ||
  path.join(
    process.env.LOCALAPPDATA || path.join(require('node:os').homedir(), 'AppData', 'Local'),
    'Programs',
    'DeepSeek Harness',
    'resources',
    'app.asar',
  );
const TERMS = process.argv.slice(2);
const CHUNK = 8 * 1024 * 1024;
const CONTEXT = Number(process.env.CTX || 900);
const MAXHIT = Number(process.env.MAXHIT || 4);

if (TERMS.length === 0) {
  console.error('need terms');
  process.exit(2);
}

const fd = fs.openSync(ASAR, 'r');
const size = fs.fstatSync(fd).size;
let carry = '';
let offset = 0;
const counts = new Map();
const total = new Map();

while (offset < size) {
  const buf = Buffer.alloc(Math.min(CHUNK, size - offset));
  fs.readSync(fd, buf, 0, buf.length, offset);
  const text = carry + buf.toString('utf8');
  for (const term of TERMS) {
    let from = 0;
    while (true) {
      const idx = text.indexOf(term, from);
      if (idx === -1) break;
      const globalPos = offset - carry.length + idx;
      counts.set(term, (counts.get(term) || 0) + 1);
      total.set(term, (total.get(term) || 0) + 1);
      if ((counts.get(term) || 0) <= MAXHIT) {
        const start = Math.max(0, idx - CONTEXT);
        const end = Math.min(text.length, idx + CONTEXT);
        const snip = text.slice(start, end).replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, '·');
        console.log('\n===== ' + term + ' @ ' + globalPos + ' =====');
        console.log(snip);
      }
      from = idx + term.length;
    }
  }
  carry = text.slice(-CONTEXT);
  offset += buf.length;
}
fs.closeSync(fd);
console.log('\n--- totals ---');
for (const [term, n] of total) console.log(n, '\t', term);
