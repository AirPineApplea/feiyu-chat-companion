// 数一下 index.js 里有多少处被 GBK 往返弄坏的多字节字符，并打出来看看。
const fs = require('node:fs');
const file = process.argv[2];
const buf = fs.readFileSync(file);
const text = buf.toString('utf8');
let bad = 0;
const spots = [];
for (let i = 0; i < text.length; i += 1) {
  if (text.charCodeAt(i) === 0xfffd) {
    bad += 1;
    if (spots.length < 40) {
      spots.push(text.slice(Math.max(0, i - 40), i + 40).replace(/[\r\n]/g, '⏎'));
    }
  }
}
console.log('替换符个数:', bad);
for (const s of spots) console.log('---', s);
