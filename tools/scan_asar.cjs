// 在 app.asar 里流式搜索关键词，输出命中处前后的片段。
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
const TERMS = ['ctx.llm', 'llm.complete', 'llm.stream'];
const CHUNK = 8 * 1024 * 1024;
const CONTEXT = 420;

const fd = fs.openSync(ASAR, 'r');
const size = fs.fstatSync(fd).size;
let carry = '';
let offset = 0;
const seen = new Map();

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
      if (!seen.has(globalPos + ':' + term)) {
        seen.set(globalPos + ':' + term, true);
        if (seen.size <= 12) {
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
console.log('\n总命中组数:', seen.size);
