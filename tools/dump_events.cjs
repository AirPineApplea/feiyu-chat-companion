// 打印会话日志里指定类型事件的真实结构（用于确认 ctx.on('session/event') 的形状）。
const fs = require('node:fs');
const path = require('node:path');
const { zstdDecompressSync } = require('node:zlib');

const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);

function decodeAll(buf) {
  const starts = [];
  let at = buf.indexOf(MAGIC);
  while (at !== -1) {
    starts.push(at);
    at = buf.indexOf(MAGIC, at + 4);
  }
  const parts = [];
  for (let i = 0; i < starts.length; i += 1) {
    const end = i + 1 < starts.length ? starts[i + 1] : buf.length;
    try {
      parts.push(zstdDecompressSync(buf.subarray(starts[i], end)).toString('utf8'));
    } catch {
      /* 残帧 */
    }
  }
  return parts.join('');
}

const group = process.argv[2];
const want = process.argv.slice(3);
const dirs = fs
  .readdirSync(group, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .sort((a, b) => b.name.localeCompare(a.name));

for (const dir of dirs) {
  const file = path.join(group, dir.name, 'session.v4.jsonl.zstd');
  if (!fs.existsSync(file)) continue;
  const lines = decodeAll(fs.readFileSync(file)).split('\n').filter(Boolean);
  console.log(`\n########## ${dir.name} · ${lines.length} 条 ##########`);
  const seen = new Set();
  for (const line of lines) {
    if (!line.startsWith('{')) continue;
    let ev;
    try {
      ev = JSON.parse(line);
    } catch {
      continue;
    }
    if (!want.includes(ev.type) || seen.has(ev.type)) continue;
    seen.add(ev.type);
    console.log(`\n----- ${ev.type} -----`);
    const text = JSON.stringify(ev, null, 1);
    console.log(text.length > 2200 ? text.slice(0, 2200) + '\n…(截断)' : text);
  }
  if (seen.size > 0) break;
}
