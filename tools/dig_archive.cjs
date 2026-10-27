// 在 app.asar 里流式搜索「会话归档」相关标识符，输出命中处前后的片段。
// 复用 scan_asar.cjs 的思路：asar 是打包文件，rg / PowerShell 都进不去，只能流式读。
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

const TERMS = process.argv.slice(2).length
  ? process.argv.slice(2)
  : ['archiveSession', 'archivedAt', 'isArchived', 'session.archive', 'archive:'];

const CHUNK = 8 * 1024 * 1024;
const CONTEXT = Number(process.env.DSH_CTX || 320);
const MAX_PER_TERM = Number(process.env.DSH_MAX || 4);

const fd = fs.openSync(ASAR, 'r');
const size = fs.fstatSync(fd).size;
let carry = '';
let offset = 0;
const counts = new Map(TERMS.map((t) => [t, 0]));
const seen = new Set();

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
      const key = globalPos + ':' + term;
      if (!seen.has(key)) {
        seen.add(key);
        const n = counts.get(term) + 1;
        counts.set(term, n);
        if (n <= MAX_PER_TERM) {
          const start = Math.max(0, idx - CONTEXT);
          const end = Math.min(text.length, idx + CONTEXT);
          const snip = text.slice(start, end).replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, '·');
          console.log('\n===== ' + term + ' @ ' + globalPos + ' =====');
          console.log(snip);
        }
      }
      from = idx + term.length;
    }
  }
  carry = text.slice(-CONTEXT);
  offset += buf.length;
}
fs.closeSync(fd);
console.log('\n=== 命中统计 ===');
for (const [term, n] of counts) console.log(`  ${term}: ${n}`);
