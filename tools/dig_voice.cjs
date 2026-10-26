// 把语音会话里她真正说过的话抽出来。
// session.v4.jsonl.zstd 是**追加写**的：一个文件里堆着很多个 zstd 帧，
// zstdDecompressSync 只解第一帧（192 字节的头），所以要按魔术字拆帧。
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
      /* 残帧，跳过 */
    }
  }
  return parts.join('');
}

/** 从一条事件的任意深度里找 pet_say 的调用参数。 */
function petSayText(event) {
  const blocks = event?.data?.content ?? event?.data?.message?.content ?? [];
  const list = Array.isArray(blocks) ? blocks : [];
  for (const block of list) {
    const name = block?.name ?? block?.toolName;
    if (name !== 'pet_say') continue;
    const args = block?.arguments ?? block?.input ?? block?.args;
    const parsed = typeof args === 'string' ? safeJson(args) : args;
    if (parsed && typeof parsed.text === 'string') return parsed.text;
  }
  return null;
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function windowOf(event) {
  const blocks = event?.data?.content ?? [];
  for (const block of Array.isArray(blocks) ? blocks : []) {
    if (typeof block?.text !== 'string') continue;
    const m = block.text.match(/现在的窗口是「([\s\S]*?)」/);
    if (m) return m[1].replace(/\s+/g, ' ').trim();
  }
  return null;
}

const group = process.argv[2];
const dirs = fs
  .readdirSync(group, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .sort((a, b) => a.name.localeCompare(b.name));

let total = 0;
for (const dir of dirs) {
  const file = path.join(group, dir.name, 'session.v4.jsonl.zstd');
  if (!fs.existsSync(file)) continue;
  const lines = decodeAll(fs.readFileSync(file)).split('\n').filter(Boolean);
  const lines2 = [];
  let currentWindow = '?';
  for (const line of lines) {
    const event = safeJson(line);
    if (!event) continue;
    const w = windowOf(event);
    if (w) currentWindow = w;
    const said = petSayText(event);
    if (said) lines2.push({ window: currentWindow, said });
  }
  console.log(`\n== ${dir.name.slice(0, 8)} · ${lines.length} 条事件 · 她说 ${lines2.length} 句`);
  for (const item of lines2) console.log(`  「${item.window.slice(0, 40)}」\n     → ${item.said}`);
  total += lines2.length;
}
console.log(`\n合计 ${total} 句`);
