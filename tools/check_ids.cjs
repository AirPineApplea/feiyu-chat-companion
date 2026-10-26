// 校验两个包的固定名（包名、路由、存盘目录、面板 id）互不重叠。
// 用法：node check_ids.cjs <目录A> <目录B>
// 路径从参数来，不写死任何人的盘符和文件夹名。
const fs = require('node:fs');

function read(p) {
  return fs.readFileSync(p, 'utf8');
}
function pick(text, re) {
  const m = text.match(re);
  return m ? m[1] : '(not found)';
}

function report(label, root) {
  const idx = read(root + '/lib/index.js');
  const cli = read(root + '/lib/client.js');
  const py = read(root + '/overlay/pet_win32.py');
  const patch = read(root + '/cordis.patch.yml');
  console.log('\n== ' + label + ' (' + root + ') ==');
  console.log('  Host name     ', pick(idx, /export const name = '([^']+)'/));
  console.log('  client id     ', pick(cli, /id: '([^']+)',/));
  console.log('  storage dir   ', pick(idx, /const STORAGE = path\.join\(DSH_HOME, 'storages', '([^']+)'\)/));
  console.log('  route prefix  ', pick(idx, /const ROUTE_PREFIX = '([^']+)'/));
  console.log('  voice dir     ', pick(idx, /const VOICE_DIR = path\.join\(DSH_HOME, '([^']+)'\)/));
  console.log('  panel id      ', pick(cli, /const PANEL_ID = '([^']+)'/));
  console.log('  client API    ', pick(cli, /const API = '([^']+)'/));
  console.log('  py state dir  ', pick(py, /STATE_DIR = os\.path\.join\(DSH_HOME, "storages", "([^"]+)"\)/));
  console.log('  patch row id  ', pick(patch, /- id: (\S+)/));
  console.log('  patch name    ', pick(patch, /name: '([^']+)'/));
  return {
    name: pick(idx, /export const name = '([^']+)'/),
    route: pick(idx, /const ROUTE_PREFIX = '([^']+)'/),
    storage: pick(idx, /const STORAGE = path\.join\(DSH_HOME, 'storages', '([^']+)'\)/),
    panel: pick(cli, /const PANEL_ID = '([^']+)'/),
  };
}

const [a, b] = process.argv.slice(2);
if (!a || !b) {
  console.error('用法: node check_ids.cjs <目录A> <目录B>');
  process.exit(2);
}

const left = report('A', a);
const right = report('B', b);

console.log('\n--- 重叠检查（有重叠就不能同时安装）---');
for (const key of Object.keys(left)) {
  const same = left[key] === right[key];
  console.log(`  ${key.padEnd(8)} ${same ? '撞了！' : '不同 ok'}  ${left[key]} / ${right[key]}`);
}
