// 从市场发现清单里抽出所有出现过的 category（用于投稿时选合法值）。
const fs = require('node:fs');
const path = require('node:path');

const file = process.argv[2];
if (!file || !fs.existsSync(file)) {
  console.error('找不到文件:', file);
  process.exit(2);
}
const text = fs.readFileSync(file, 'utf8');
const cats = new Map();
for (const m of text.matchAll(/"category"\s*:\s*"([^"]+)"/g)) {
  cats.set(m[1], (cats.get(m[1]) || 0) + 1);
}
console.log('文件:', path.basename(file));
console.log('category 取值：');
for (const [k, n] of [...cats.entries()].sort((a, b) => b[1] - a[1])) {
  console.log('  ' + k.padEnd(20) + n);
}
if (cats.size === 0) console.log('  （没有 category 字段）');
