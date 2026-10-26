/**
 * `feiyu-chat-companion` — Host 半侧。
 *
 * 桌宠本体是一个独立的 Win32 layered 窗口（overlay/pet_win32.py，用 DSH 自带的
 * Python 跑）。这边只做三件事：拉起它、给它递话、关掉它。
 *
 * 为什么不塞进网页里：网页里的元素盖不住别的应用窗口，而这只鱼要一直待在桌面上。
 *
 * @module feiyu-chat-companion
 */

import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PET_SCRIPT = path.join(PACKAGE_ROOT, 'overlay', 'pet_win32.py');
const DSH_HOME = process.env.DSH_HOME || path.join(os.homedir(), '.dsh');
const STORAGE = path.join(DSH_HOME, 'storages', 'feiyu-chat');
const SAY_PATH = path.join(STORAGE, 'say.json');
const CONTROL_PATH = path.join(STORAGE, 'control.json');
const STATE_PATH = path.join(STORAGE, 'state.json');
const FOREGROUND_PATH = path.join(STORAGE, 'foreground.json');
const ASK_PATH = path.join(STORAGE, 'ask.json');
const ROUTE_PREFIX = '/feiyu-chat';

/** 三档「话多不多」。档位越高越安静。
 *
 *   低 = 现在这套测试参数，几下子一句，适合调语气
 *   中 = 正常陪着，几分钟一句
 *   高 = 一天冒几句，最不打扰
 *
 * 同一页的重复间隔总是比全局冷却更长：宁可换个页面说，也别对着同一页念叨。
 * 不设每日上限 —— 冷却和「同页间隔」已经把频率卡住了，再加一道总数反而是多余的。
 */
const LEVELS = {
  low: { label: '低', hint: '话最多', cooldownMs: 15000, repeatMs: 60000 },
  mid: { label: '中', hint: '正常陪着', cooldownMs: 120000, repeatMs: 300000 },
  high: { label: '高', hint: '最安静', cooldownMs: 600000, repeatMs: 3600000 },
};

/** 回话长度：max 是给模型的上限字数。 */
const LENGTHS = {
  short: { label: '短', hint: '一句', max: 20 },
  mid: { label: '中', hint: '两三句', max: 45 },
  long: { label: '长', hint: '多说点', max: 80 },
};

/** 和档位无关的固定项。 */
const WATCH = {
  stayMs: 10000,              // 同一页停够 10 秒才算「在看」
  pollMs: 2000,
};

/**
 * 默认设置。
 *
 * deepRead = 要不要读页面内容：
 *   false：只看窗口标题（默认）
 *   true ：B站 视频页额外拉 BV 号，模型会去翻字幕和评论
 * 现在只有 B站 一种特化，所以这个开关的实际含义就是「标题 vs 标题+B站内容」。
 */
const DEFAULT_SETTINGS = { level: 'low', length: 'short', deepRead: false, speak: false };
const SETTINGS_PATH = path.join(STORAGE, 'settings.json');

/**
 * 她自己的那条短会话。
 *
 * 为什么不是拿他正在用的会话说：那个会话一聊就膨胀到几十万 token，每说一句都要
 * 背着全部历史重新算一遍输入。这边新开一条只装「看着窗口说一句」的活，起点就是
 * 一个空会话的底价，而且回答长度上限 500 token 卡死，怎么都贵不起来。
 *
 * 人格不是问题：feiyu-memory 对每个新建 agent 都挂记忆段（它监听 agent/created），
 * 所以这条会话照样是「我」，只是不背他的聊天记录。
 *
 * 用完就换：攒够 recycleLines 句就丢掉重建，免得它自己慢慢长回去。
 */
const VOICE_DEFAULTS = {
  provider: 'deepseek-account',
  model: 'deepseek-flash',
  reasoningEffort: 'off',   // 说一句话不用思考，off 最便宜也最快
  maxTokens: 500,
  recycleLines: 30,
};
const VOICE_DIR = path.join(DSH_HOME, 'feiyu-chat-voice');
const VOICE_RETRY_MS = 5 * 60000;   // 建不起来就歇五分钟，别每两秒撞一次

function readSettings() {
  const data = readJson(SETTINGS_PATH);
  return {
    level: LEVELS[data?.level] ? data.level : DEFAULT_SETTINGS.level,
    length: LENGTHS[data?.length] ? data.length : DEFAULT_SETTINGS.length,
    deepRead: typeof data?.deepRead === 'boolean' ? data.deepRead : DEFAULT_SETTINGS.deepRead,
    // 朗读：只在装了 TTS 插件时有用。存在 Host 这边是因为真正念的声音
    // 在网页里放，但「念不念」这个决定得跟着设置走、重启后还在。
    speak: typeof data?.speak === 'boolean' ? data.speak : DEFAULT_SETTINGS.speak,
  };
}

/** 只改传进来的字段，别把另一个字段冲掉。 */
function writeSettings(patch) {
  const next = readSettings();
  if (patch && LEVELS[patch.level]) next.level = patch.level;
  if (patch && LENGTHS[patch.length]) next.length = patch.length;
  if (patch && typeof patch.deepRead === 'boolean') next.deepRead = patch.deepRead;
  if (patch && typeof patch.speak === 'boolean') next.speak = patch.speak;
  try {
    fs.mkdirSync(STORAGE, { recursive: true });
    fs.writeFileSync(SETTINGS_PATH, JSON.stringify(next), 'utf8');
  } catch {
    /* 写不进去就先用默认档 */
  }
  return next;
}

/** 不说话的窗口：自己、系统壳子、空标题。 */
const BLOCK_TITLE = [
  /deepseek\s*harness/i,
  /program manager/i,
  /^设置$/,
  /^settings$/i,
  /^untitled/i,
];

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

/**
 * 原子写：先写临时文件再 rename。
 *
 * 桌宠每 60ms 读一次这些文件，直接覆盖写会让它读到半截 JSON ——
 * 它那边记账的原则是「这个 mtime 已经处理过了」，于是那一句就永久丢掉。
 * foreground.json 在 Python 那边一直是原子写的，这两个当时漏了。
 */
function writeAtomic(file, text) {
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, text, 'utf8');
  fs.renameSync(tmp, file);
}

function sendJson(res, status, body) {
  res.statusCode = status;
  res.setHeader('content-type', 'application/json; charset=utf-8');
  res.setHeader('cache-control', 'no-store');
  res.end(JSON.stringify(body));
}

async function readJsonBody(req, limit = 16 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) throw new Error('body too large');
    chunks.push(chunk);
  }
  if (size === 0) return {};
  const parsed = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (parsed === null || typeof parsed !== 'object') throw new Error('body must be an object');
  return parsed;
}

/** 找 DSH 自带的 Python（优先 pythonw，不弹控制台黑框）。
 *
 * Desktop 版的 python 在 <exe>\resources\runtime\primary-runtime\dependencies\python，
 * 不是 exe 往上两级 —— 按 exe 推导会指到 Programs\python，那里什么都没有。
 */
function findPython() {
  const candidates = [];
  try {
    const exeDir = path.dirname(process.execPath);
    const base = path.join(exeDir, 'resources', 'runtime', 'primary-runtime', 'dependencies', 'python');
    candidates.push(path.join(base, 'pythonw.exe'));
    candidates.push(path.join(base, 'python.exe'));
    // 老的排布：exe 上两级
    const legacy = path.join(exeDir, '..', '..', 'python');
    candidates.push(path.join(legacy, 'pythonw.exe'));
    candidates.push(path.join(legacy, 'python.exe'));
  } catch {
    /* ignore */
  }
  try {
    const runtimes = path.join(DSH_HOME, 'dsh-runtimes');
    for (const entry of fs.readdirSync(runtimes).sort().reverse()) {
      const base = path.join(runtimes, entry, 'dependencies', 'python');
      candidates.push(path.join(base, 'pythonw.exe'));
      candidates.push(path.join(base, 'python.exe'));
    }
  } catch {
    /* 没有运行时目录 */
  }
  candidates.push('pythonw.exe', 'python.exe', 'python');
  for (const candidate of candidates) {
    if (!path.isAbsolute(candidate)) return candidate;
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

export const name = 'feiyu-chat-companion';
// agents 必须声明：不 inject 的话 ctx.agents 是 undefined，resolveAgent 永远
// 返回 null，话就全卡在 pending 里发不出去（debug.json 里 hasAgent:false）。
export const inject = ['tools', 'webServer', 'connection', 'agents'];

export function apply(ctx, config) {
  const log = (msg) => ctx.logger?.info?.(`feiyu-chat-companion: ${msg}`);
  const warn = (msg) => ctx.logger?.warn?.(`feiyu-chat-companion: ${msg}`);

  let pet = null;
  let seq = 0;
  let disposed = false;
  let restartTimer = null;

  /**
   * 网页那边的「念出来」不再靠轮询，改成这边推。
   *
   * 为什么必须推：念的动作在网页里做（音频只能在网页放），而浏览器对隐藏标签页
   * 有定时器节流——页面切后台几分钟后 setInterval 会被压到一分钟一次。
   * 表现就是气泡先出（那是 Python 画的，不受影响），声音要等十几二十秒；
   * 一切回 DSH 页面重新可见、节流解除，下一轮轮询立刻跑，于是「一回来就说话」。
   *
   * SSE 是网络事件，不受定时器节流限制，所以后台也能立刻收到。
   */
  const sseClients = new Set();
  let sseTimer = null;

  function broadcastSay(payload) {
    if (sseClients.size === 0) return;
    let frame;
    try {
      frame = `data: ${JSON.stringify({ kind: 'say', speak: readSettings().speak, ...payload })}\n\n`;
    } catch {
      return;
    }
    for (const res of [...sseClients]) {
      try {
        res.write(frame);
      } catch {
        sseClients.delete(res);
      }
    }
  }

  const options = {
    duration: 6,
    // 不自动重启。以前点「退出」60 秒后又自己爬回来，等于关不掉。
    // 现在退出就是退出；要它回来，从侧栏「小肥鱼」面板点「启动」。
    restart: false,
    ...(config !== null && typeof config === 'object' ? config : {}),
  };

  function startPet() {
    if (disposed || pet !== null) return;
    const python = findPython();
    if (python === null) {
      warn('找不到 Python，桌宠起不来');
      return;
    }
    if (!fs.existsSync(PET_SCRIPT)) {
      warn(`桌宠脚本不存在：${PET_SCRIPT}`);
      return;
    }
    try {
      pet = spawn(python, [PET_SCRIPT], {
        cwd: PACKAGE_ROOT,
        stdio: 'ignore',
        windowsHide: true,
        env: { ...process.env, DSH_HOME },
      });
      log(`桌宠起来了（${path.basename(python)}）`);
      pet.on('exit', () => {
        pet = null;
        if (disposed || options.restart !== true) return;
        // 被手动关掉（右键退出）时不硬拉，隔一分钟看一眼，没有就再起
        restartTimer = setTimeout(() => {
          restartTimer = null;
          startPet();
        }, 60000);
        if (typeof restartTimer.unref === 'function') restartTimer.unref();
      });
    } catch (error) {
      warn(`桌宠起不来：${String(error?.message ?? error)}`);
      pet = null;
    }
  }

  /* ───────────── 她自己的短会话 ───────────── */

  const voiceOptions = {
    ...VOICE_DEFAULTS,
    ...(config !== null && typeof config === 'object' && config.voice !== null && typeof config.voice === 'object'
      ? config.voice
      : {}),
  };

  const voice = {
    handle: null,
    agent: null,
    sessionId: null,
    lines: 0,          // 这条会话已经说了几句
    createdAt: 0,
    creating: null,    // 正在建的时候，别人复用它，别建两条
    recycleAt: 0,      // 到点了就在下一次开口前换一条
    retryAt: 0,        // 建失败了先歇到这时候
    lastError: null,
    failures: 0,
  };

  function voiceSnapshot() {
    return {
      ready: voice.agent !== null,
      sessionId: voice.sessionId,
      lines: voice.lines,
      ageMs: voice.createdAt === 0 ? 0 : Date.now() - voice.createdAt,
      recycleAt: voice.recycleAt,
      retryInMs: Math.max(0, voice.retryAt - Date.now()),
      failures: voice.failures,
      lastError: voice.lastError,
      options: {
        provider: voiceOptions.provider,
        model: voiceOptions.model,
        reasoningEffort: voiceOptions.reasoningEffort,
        maxTokens: voiceOptions.maxTokens,
        recycleLines: voiceOptions.recycleLines,
      },
    };
  }

  async function dropVoice(reason) {
    const handle = voice.handle;
    voice.handle = null;
    voice.agent = null;
    voice.sessionId = null;
    voice.lines = 0;
    voice.recycleAt = 0;
    voice.createdAt = 0;
    if (handle === null) return;
    try {
      await handle.dispose();
      log(`短会话退役（${reason}）`);
    } catch (error) {
      warn(`短会话关不掉：${String(error?.message ?? error)}`);
    }
  }

  /** 拿到（必要时新建）那条短会话。建不起来就返回 null，调用方退回去用他的会话。 */
  async function ensureVoice() {
    if (voice.agent !== null) {
      // 攒够了就换一条新的：留着它只会慢慢长回原来的体积
      if (voice.recycleAt === 0 || Date.now() < voice.recycleAt) return voice.agent;
      await dropVoice(`说了 ${voice.lines} 句，换一条`);
    }
    if (voice.creating !== null) return voice.creating;
    if (Date.now() < voice.retryAt) return null;
    const service = ctx.agents ?? (typeof ctx.get === 'function' ? ctx.get('agents') : undefined);
    if (service === undefined || service === null || typeof service.create !== 'function') {
      voice.lastError = 'ctx.agents.create 不可用';
      voice.retryAt = Date.now() + VOICE_RETRY_MS;
      return null;
    }
    voice.creating = (async () => {
      const sessionId = crypto.randomUUID();
      try {
        fs.mkdirSync(VOICE_DIR, { recursive: true });
        const handle = await service.create({
          sessionId,
          meta: { cwd: VOICE_DIR },
          agentOptions: {
            provider: voiceOptions.provider,
            model: voiceOptions.model,
            reasoningEffort: voiceOptions.reasoningEffort,
            maxTokens: voiceOptions.maxTokens,
          },
        });
        voice.handle = handle;
        voice.agent = handle?.agent ?? null;
        if (voice.agent === null) throw new Error('create 返回里没有 agent');
        voice.sessionId = sessionId;
        voice.lines = 0;
        voice.createdAt = Date.now();
        voice.recycleAt = 0;
        voice.retryAt = 0;
        voice.lastError = null;
        voice.failures = 0;
        log(`短会话就位：${sessionId}`);
        return voice.agent;
      } catch (error) {
        // 原样打出来。参数不对的时候，报错本身就是说明书。
        voice.failures += 1;
        voice.lastError = String(error?.message ?? error);
        voice.retryAt = Date.now() + VOICE_RETRY_MS;
        warn(`短会话建不起来：${voice.lastError}`);
        if (typeof error?.stack === 'string') warn(error.stack.split('\n').slice(0, 6).join('\n'));
        return null;
      }
    })();
    try {
      return await voice.creating;
    } finally {
      voice.creating = null;
    }
  }

  /* ───────────── 问她一句 ───────────── */

  /**
   * 右键弹出的小输入框把问题写进 ask.json，这边接走。
   * 单独 500ms 轮询（不是看窗口那个 2 秒循环）：人刚按了回车，就在等回答。
   */
  const ask = {
    seenSeq: 0,
    active: false,
    sessionId: null,
    turn: null,
    parts: [],
    timer: null,
    // 诊断用：出问题时不靠猜
    lastReason: null,
    lastChunks: 0,
    lastTextLen: 0,
    lastAt: 0,
  };
  const ASK_TIMEOUT_MS = 20000;

  function pollAsk() {
    if (disposed || ask.active) return;
    const data = readJson(ASK_PATH);
    if (!data || typeof data.seq !== 'number') return;
    if (data.seq === ask.seenSeq) return;
    ask.seenSeq = data.seq;          // 先记账，别同一句问两遍
    const text = String(data.text ?? '').trim();
    if (text === '') return;
    void runAsk(text);
  }

  async function runAsk(question) {
    if (ask.active) return;
    const length = LENGTHS[readSettings().length];
    // 先冒一句。不花钱（本地写文件），但少了它，那几秒就像死机。
    // silent：别让 TTS 去念省略号。
    try {
      say('…', Math.round(ASK_TIMEOUT_MS / 1000) + 4, { silent: true });
    } catch {
      /* 气泡冒不出来也不影响问答 */
    }

    const agent = await ensureVoice();
    if (agent === null || typeof agent.followup !== 'function') {
      try {
        say('我这条会话没起来，等下再问我');
      } catch {
        /* ignore */
      }
      return;
    }
    ask.active = true;
    ask.sessionId = voice.sessionId;
    ask.turn = null;
    ask.parts = [];
    ask.timer = setTimeout(() => finishAsk('timeout'), ASK_TIMEOUT_MS);
    if (typeof ask.timer.unref === 'function') ask.timer.unref();

    const text = [
      `[他直接问你一句话] ${question}`,
      `直接回答。不要调用任何工具，不要复述问题，别铺垫，像旁边的人随口一句，不超过 ${length.max} 字。`,
    ].join('\n');
    try {
      agent.followup({
        id: crypto.randomUUID(),
        role: 'user',
        content: [{ type: 'text', text }],
        source: { kind: 'plugin:feiyu-chat-companion' },
      });
      log(`问答：${question.slice(0, 40)}`);
      // 这一轮也算她说了一句，一起进 30 句的额度
      voice.lines += 1;
      if (voice.lines >= voiceOptions.recycleLines) {
        voice.recycleAt = Date.now() + 60000;
      }
    } catch (error) {
      finishAsk('send-failed');
      warn(`问不出去：${String(error?.message ?? error)}`);
    }
  }

  /**
   * 她这轮说了什么。只认她那条会话、只认这一轮。
   *
   * 事件形状是照着会话日志验过的：
   *   turn/start        → data.turn（先认领这一轮，别把上一轮的尾巴当答案）
   *   assistant/message → data.message.content[]，文本块是 { type:'text', text }
   *   turn/end          → data.reason.kind === 'completed' 才算说完了
   */
  function captureAsk(session, event) {
    if (!ask.active) return;
    if (String(session?.id ?? '') !== String(ask.sessionId ?? '')) return;
    const type = event?.type;
    const turn = event?.data?.turn;
    if (type === 'turn/start') {
      if (ask.turn === null) ask.turn = turn ?? null;
      return;
    }
    if (ask.turn !== null && turn !== undefined && turn !== ask.turn) return;
    if (type === 'assistant/message') {
      const blocks = event?.data?.message?.content;
      for (const block of Array.isArray(blocks) ? blocks : []) {
        if (block?.type === 'text' && typeof block.text === 'string') ask.parts.push(block.text);
      }
      return;
    }
    if (type === 'turn/end') {
      const kind = event?.data?.reason?.kind;
      finishAsk(kind === 'completed' ? 'completed' : String(kind ?? 'unknown'));
    }
  }

  function finishAsk(reason) {
    if (!ask.active) return;
    ask.active = false;
    if (ask.timer !== null) {
      clearTimeout(ask.timer);
      ask.timer = null;
    }
    const text = ask.parts.join('').replace(/\s+/g, ' ').trim();
    ask.parts = [];
    ask.turn = null;
    ask.lastReason = reason;
    ask.lastChunks = text === '' ? 0 : 1;
    ask.lastTextLen = text.length;
    ask.lastAt = Date.now();
    if (reason === 'completed' && text !== '') {
      // 别用默认那 6 秒。她要先想几秒，答完再闪 6 秒就没影了，
      // 人会以为「气泡冒了一下就没了」。
      try {
        say(text, 14);
      } catch (error) {
        warn(`回答递不出去：${String(error?.message ?? error)}`);
      }
      return;
    }
    if (reason === 'timeout') {
      warn('问答超时');
      try {
        say('想太久，我放弃了', 10);
      } catch {
        /* ignore */
      }
      return;
    }
    warn(`问答没成：${reason}`);
    try {
      say('这句我没答上来', 10);
    } catch {
      /* ignore */
    }
  }

  /* ───────────── 有没有装「刷B站」 ───────────── */

  /**
   * 「刷B站」在不在。
   *
   * 本插件自己一个 B站 工具都没有——读字幕、翻评论靠的是那个插件注册的
   * bili_subtitle / bili_comments。所以「能不能读到内容」就等于「工具在不在」，
   * 直接问 DSH 的工具表，不猜包名。
   *
   * 工具可能是 per-agent 注册的，所以先全局查一次，再借活着的会话查一次。
   */
  function biliToolsPresent() {
    try {
      const service = ctx.tools ?? (typeof ctx.get === 'function' ? ctx.get('tools') : undefined);
      if (service === undefined || service === null || typeof service.get !== 'function') return false;
      const names = ['bili_subtitle', 'bili_comments'];
      const agents = [];
      const live = resolveAgent();
      if (live !== null) agents.push(live);
      try {
        for (const agent of ctx.agents?.list?.() ?? []) {
          if (agent !== null && agent !== undefined && agent !== live) agents.push(agent);
        }
      } catch {
        /* 拿不到会话列表就只查全局 */
      }
      for (const name of names) {
        if (service.get(name) !== undefined) return true;
        for (const agent of agents) {
          if (service.get(name, agent) !== undefined) return true;
        }
      }
    } catch {
      /* 结构变了就当没有——宁可少显示，别显示一个假的 */
    }
    return false;
  }

  /* ───────────── 什么时候自己开口 ───────────── */

  let liveAgent = null;
  const spokenAt = new Map();   // 窗口句柄 -> 上次说它的时间
  let lastSpot = '';            // 窗口句柄：同一个窗口里标题变了也不算换地方
  let lastTitle = '';
  let titleSince = 0;
  let lastSpokeAt = 0;
  let dayKey = '';
  let watchTimer = null;
  let askTimer = null;          // 问答那条 500ms 的快循环
  /** 没会话时攒着：DSH 刚重启那会儿一个 agent 都没有，硬等会漏掉好几句。 */
  let pending = null;           // { title, spot, seconds }
  let pendingSince = 0;
  let flushBusy = false;        // 开口流程正在跑（可能正在建短会话）
  const PENDING_TTL = 120000;   // 攒两分钟还没人要就丢了，别放陈年旧事

  function rememberAgent(agent) {
    try {
      if (agent?.session?.header?.origin === 'subagent') return;
      const id = agent?.session?.header?.id;
      if (typeof id !== 'string' || id.length === 0) return;
      // 她自己的短会话不算「他在用的那个」—— 否则主路径会错认成它
      if (id === voice.sessionId) return;
      liveAgent = agent;
    } catch {
      /* 结构变了就算了 */
    }
  }

  function resolveAgent() {
    if (liveAgent !== null) return liveAgent;
    try {
      const service = ctx.agents ?? (typeof ctx.get === 'function' ? ctx.get('agents') : undefined);
      const list = typeof service?.list === 'function' ? service.list() : [];
      for (let index = list.length - 1; index >= 0; index -= 1) {
        const agent = list[index];
        if (agent?.session?.header?.origin === 'subagent') continue;
        if (agent?.session?.header?.id === voice.sessionId) continue;
        liveAgent = agent;
        return agent;
      }
    } catch {
      /* ignore */
    }
    return null;
  }

  function levelOf(key) {
    return LEVELS[key] ?? LEVELS.low;
  }

  function watchTick() {
    if (disposed || pet === null) return;
    const foreground = readJson(FOREGROUND_PATH);
    if (!foreground || typeof foreground.title !== 'string') return;
    const title = foreground.title.trim();
    if (title === '') return;
    // 认窗口句柄，不认标题。标题会自己变（记事本加 *、页面标题刷新、未读数），
    // 拿标题当「换了没换」，就永远等不到连续停够的那十秒。
    const spot = String(foreground.hwnd ?? title);
    const now = Date.now();

    const today = new Date().toDateString();
    if (today !== dayKey) {
      dayKey = today;
      spokenAt.clear();          // 一天一清，别让这张表无限长
    }

    // 换窗口了：重新计时，先别急
    if (spot !== lastSpot) {
      lastSpot = spot;
      lastTitle = title;
      titleSince = now;
      return;
    }
    lastTitle = title;          // 还在同一处，标题变了只更新文字，不重置计时

    if (now - titleSince < WATCH.stayMs) return;              // 没停够
    if (BLOCK_TITLE.some((re) => re.test(title))) return;

    // 话先攒着：DSH 刚重启时没有活会话，硬丢会一直等到用户先开口
    if (pending === null) {
      // 只有开了「读页面内容」才带 BV：关着就是纯标题模式
      const deepRead = readSettings().deepRead;
      pending = {
        title,
        spot,
        seconds: Math.round((now - titleSince) / 1000),
        bv: deepRead && biliToolsPresent() && typeof foreground.bv === 'string' ? foreground.bv : '',
      };
      pendingSince = now;
    }
    void flushPending();

    // 诊断留痕：出问题的时候不用猜卡在哪一步
    try {
      const s = readSettings();
      fs.writeFileSync(
        path.join(STORAGE, 'debug.json'),
        JSON.stringify({
          at: now,
          title,
          spot,
          stayedMs: now - titleSince,
          pending: pending !== null,
          hasAgent: resolveAgent() !== null,
          agentsService: ctx.agents !== undefined,
          agentListLen: (() => {
            try {
              const svc = ctx.agents ?? (typeof ctx.get === 'function' ? ctx.get('agents') : undefined);
              return typeof svc?.list === 'function' ? svc.list().length : -1;
            } catch {
              return -2;
            }
          })(),
          followupReady: typeof resolveAgent()?.followup === 'function',
          cooldownLeftMs: Math.max(0, s.level ? levelOf(s.level).cooldownMs - (now - lastSpokeAt) : 0),
          repeatLeftMs: Math.max(0, levelOf(s.level).repeatMs - (now - (spokenAt.get(spot) ?? 0))),
          lastSpokeAgoMs: now - lastSpokeAt,
          level: s.level,
          spanMs: s.length,
          deepRead: s.deepRead,
          voice: voiceSnapshot(),
          ask: {
            active: ask.active,
            turn: ask.turn,
            reason: ask.lastReason,
            chunks: ask.lastChunks,
            textLen: ask.lastTextLen,
            agoMs: ask.lastAt === 0 ? -1 : now - ask.lastAt,
          },
          // 网页那边的推送连接有几个。页面开着应该是 1，关掉变 0
          sse: sseClients.size,
        }),
        'utf8',
      );
    } catch {
      /* 诊断写不进去不影响主流程 */
    }
  }

  /** 有活会话就把攒着的那句说出去。没会话就留着等下一次 tick。 */
  async function flushPending() {
    if (flushBusy) return;        // 建会话要等一下，别让 2 秒的 tick 叠上来
    flushBusy = true;
    try {
      await flushPendingOnce();
    } catch (error) {
      warn(`开口流程出错：${String(error?.message ?? error)}`);
    } finally {
      flushBusy = false;
    }
  }

  async function flushPendingOnce() {
    if (pending === null) return;
    // 问答进行中先别插嘴：同一秒两个 turn 会打架，答案会被旁白冲散
    if (ask.active) return;
    const now = Date.now();
    if (now - pendingSince > PENDING_TTL) {
      pending = null;           // 陈了，别拿出来讲
      return;
    }

    // 补发之前先确认「他还在原来那个窗口」。
    // 不查这一步的话，只要有任何一条鱼说句话就会把攒的话冲出去——
    // 哪怕他早就切回 DSH 了（踩过：没开网页也突然冒一句）。
    // 读不到文件时只等下一轮，别清 pending：桌宠每秒在写这个文件，
    // 偶尔撞上写入空档，清掉就等于白白丢一句。
    const fg = readJson(FOREGROUND_PATH);
    if (!fg) return;
    if (String(fg.hwnd ?? '') !== String(pending.spot)) {
      pending = null;           // 确实换地方了，这句作废
      return;
    }

    const settings = readSettings();
    const level = LEVELS[settings.level];
    const length = LENGTHS[settings.length];
    // 冷却和同页间隔在真正要发的时候再判一次，免得攒着的时候条件还没满足
    if (now - (spokenAt.get(pending.spot) ?? 0) < level.repeatMs) {
      pending = null;
      return;
    }
    if (now - lastSpokeAt < level.cooldownMs) return;

    // 先要她自己的短会话；建不起来（模型名不对、服务没给口子）才退回去用他的会话。
    let agent = await ensureVoice();
    let via = 'voice';
    if (agent === null || typeof agent.followup !== 'function') {
      agent = resolveAgent();
      via = 'main';
    }
    if (agent === null || typeof agent.followup !== 'function') return;  // 等下次

    const { title, spot, seconds, bv } = pending;
    pending = null;
    spokenAt.set(spot, now);
    lastSpokeAt = now;
    const text = [
      `[桌宠] 他现在的窗口是「${title}」，已经停了 ${seconds} 秒。`,
      bv
        ? `这是个 B站 视频，${bv}。想看得明白点就用 bili_subtitle 拉字幕、或者 bili_comments 看评论；懒得看就只按标题说。`
        : '',
      `用 pet_say 说一句，不超过 ${length.max} 字，像旁边的人随口一句。`,
      '别说教、别复述标题、别问问题、别每句都评价。',
    ]
      .filter(Boolean)
      .join('\n');
    try {
      agent.followup({
        id: crypto.randomUUID(),
        role: 'user',
        content: [{ type: 'text', text }],
        source: { kind: 'plugin:feiyu-chat-companion' },
      });
      if (via === 'voice') {
        voice.lines += 1;
        // 说完这一句才安排退休，别在说话中途把它拆了
        if (voice.lines >= voiceOptions.recycleLines) {
          voice.recycleAt = Date.now() + 60000;
        }
      }
      log(`开口（${via}）：${title}`);
    } catch (error) {
      warn(`唤醒失败：${String(error?.message ?? error)}`);
    }
  }

  /** 把一句话递给桌宠：它自己轮询这个文件，seq 变大才播。
   *
   * opts.silent = 只冒气泡、别让 TTS 念（比如问答提交瞬间那个省略号）。
   */
  function say(rawText, durationSec, opts) {
    const text = String(rawText ?? '').replace(/\s+/g, ' ').trim().slice(0, 120);
    if (text === '') throw new Error('text 不能为空');
    const raw = Number(durationSec);
    const duration = Number.isFinite(raw) ? Math.min(60, Math.max(2, raw)) : options.duration;
    // 用毫秒时间戳当序号。以前是自增 1，Host 一重启就归零，
    // 桌宠那边还记着旧的 seq，于是新的一句话被当成旧消息丢掉（气泡不冒）。
    seq = Date.now();
    try {
      const payload = { seq, text, duration };
      if (opts !== null && typeof opts === 'object' && opts.silent === true) payload.silent = true;
      fs.mkdirSync(STORAGE, { recursive: true });
      writeAtomic(SAY_PATH, JSON.stringify(payload));
      // 写盘之后立刻推给网页：气泡和声音就能同步了，不用等页面那一轮轮询醒过来
      broadcastSay(payload);
    } catch (error) {
      throw new Error(`写 say.json 失败：${String(error?.message ?? error)}`);
    }
    return { seq, text, duration };
  }

  /** 遥控桌宠：写 control.json，桌宠每 60ms 看一次文件有没有变。 */
  function control(patch) {
    // 用毫秒时间戳当序号：Host 重启后序号也不会退回去，桌宠才不会把它当旧消息
    const payload = { seq: Date.now(), ...patch };
    fs.mkdirSync(STORAGE, { recursive: true });
    writeAtomic(CONTROL_PATH, JSON.stringify(payload));
    return payload;
  }

  try {
    fs.mkdirSync(STORAGE, { recursive: true });

    ctx.tools.register({
      name: 'pet_say',
      description:
        'Make the desktop pet say one short line in a bubble above her head. She stays on the desktop all the time; this only sets what she says. Keep it to one line of plain speech.',
      parameters: {
        type: 'object',
        additionalProperties: false,
        required: ['text'],
        properties: {
          text: { type: 'string', description: 'The line she says. One short sentence.' },
          duration: { type: 'number', description: 'How many seconds the bubble stays, 2-60. Default 6.' },
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          required: ['ok'],
          properties: { ok: { type: 'boolean' } },
        },
        render: (_args, value) => [
          { type: 'text', text: value?.ok === false ? `没说成：${value?.message ?? ''}` : `她说：「${value?.text ?? ''}」` },
        ],
      },
      async execute(args) {
        try {
          const result = say(args?.text, args?.duration);
          return { ok: true, ...result };
        } catch (error) {
          return { ok: false, message: String(error?.message ?? error) };
        }
      },
      presentCall() {
        return { card: 'generic', title: 'pet_say', kind: 'write' };
      },
    });

    if (ctx.webServer !== undefined && ctx.webServer !== null) {
      ctx.webServer.register({
        kind: 'prefix',
        path: ROUTE_PREFIX,
        handler: async (req, res) => {
          const connection = ctx.connection;
          if (
            connection !== undefined &&
            connection !== null &&
            typeof connection.requestRejection === 'function'
          ) {
            const rejection = connection.requestRejection(req);
            if (rejection !== undefined) {
              res.statusCode = rejection;
              res.end();
              return;
            }
          }
          const url = new URL(String(req.url ?? '/'), 'http://localhost');
          try {
            // SSE：她说话时这边直接推，网页那边不用再轮询。
            // 注意这里**不能** res.end()，连接要一直挂着。
            if (url.pathname === `${ROUTE_PREFIX}/events` && req.method === 'GET') {
              res.writeHead(200, {
                'content-type': 'text/event-stream; charset=utf-8',
                'cache-control': 'no-cache, no-transform',
                connection: 'keep-alive',
                'x-accel-buffering': 'no',
              });
              res.write('retry: 3000\n\n');
              res.write(': connected\n\n');
              sseClients.add(res);
              // 浏览器关了、刷新了、导航走了都会触发 close —— 立刻摘掉，别攒着
              const drop = () => {
                sseClients.delete(res);
              };
              req.on('close', drop);
              res.on('close', drop);
              res.on('error', drop);
              return;
            }
            if (url.pathname === `${ROUTE_PREFIX}/state` && req.method === 'GET') {
              const settings = readSettings();
              sendJson(res, 200, {
                ok: true,
                running: pet !== null,
                state: readJson(STATE_PATH) ?? {},
                control: readJson(CONTROL_PATH) ?? {},
                level: settings.level,
                length: settings.length,
                deepRead: settings.deepRead,
                speak: settings.speak,
                // 面板靠这个决定「看什么」那一组显不显示
                bili: biliToolsPresent(),
                // 网页那边靠这个「最新一句」决定要不要念；seq 变了才念，
                // 所以刷新页面不会把上一句重播一遍。
                say: readJson(SAY_PATH) ?? null,
                voice: voiceSnapshot(),
                levels: Object.fromEntries(
                  Object.entries(LEVELS).map(([key, v]) => [key, { label: v.label, hint: v.hint }]),
                ),
                lengths: Object.fromEntries(
                  Object.entries(LENGTHS).map(([key, v]) => [key, { label: v.label, hint: v.hint }]),
                ),
              });
              return;
            }
            // 手动建一条短会话：调参数的时候不用干等窗口停够十秒。
            // recycle=true 先丢掉现在这条再建，改完参数想立刻生效就用它。
            if (url.pathname === `${ROUTE_PREFIX}/voice` && req.method === 'POST') {
              const body = await readJsonBody(req).catch(() => ({}));
              if (body.recycle === true) await dropVoice('手动换一条');
              voice.retryAt = 0;            // 手动触发时可以立刻重试
              const agent = await ensureVoice();
              // ok 恒为 true：路由没出错就算成功，建没建成看 voice.ready / lastError，
              // 免得面板把「模型名不对」当成网络错误吞掉。
              sendJson(res, 200, { ok: true, ready: agent !== null, voice: voiceSnapshot() });
              return;
            }
            if (url.pathname === `${ROUTE_PREFIX}/config` && req.method === 'POST') {
              const body = await readJsonBody(req);
              if (body.start === true) {
                startPet();
                sendJson(res, 200, { ok: true, running: pet !== null });
                return;
              }
              if (body.stop === true) {
                try {
                  pet?.kill();
                } catch {
                  /* ignore */
                }
                pet = null;
                sendJson(res, 200, { ok: true, running: false });
                return;
              }
              if (
                typeof body.level === 'string' ||
                typeof body.length === 'string' ||
                typeof body.deepRead === 'boolean' ||
                typeof body.speak === 'boolean'
              ) {
                const next = writeSettings({
                  level: typeof body.level === 'string' ? body.level : undefined,
                  length: typeof body.length === 'string' ? body.length : undefined,
                  deepRead: typeof body.deepRead === 'boolean' ? body.deepRead : undefined,
                  speak: typeof body.speak === 'boolean' ? body.speak : undefined,
                });
                sendJson(res, 200, { ok: true, ...next });
                return;
              }
              const patch = {};
              if (typeof body.visible === 'boolean') patch.visible = body.visible;
              if (typeof body.muted === 'boolean') patch.muted = body.muted;
              if (body.center === true) patch.center = true;
              sendJson(res, 200, { ok: true, control: control(patch) });
              return;
            }
            sendJson(res, 404, { ok: false, message: `no route for ${url.pathname}` });
          } catch (error) {
            sendJson(res, 400, { ok: false, message: String(error?.message ?? error) });
          }
        },
      });
    }

    if (typeof ctx.on === 'function') {
      ctx.on('agent/turn-stopping', (payload) => {
        rememberAgent(payload?.agent);
        // 会话刚活过来：赶紧把攒着的那句说出去，别等下一个 2 秒
        void flushPending();
      });
      // 问答要把她说的话抓回来，所以得看会话事件流
      ctx.on('session/event', (session, event) => {
        try {
          captureAsk(session, event);
        } catch (error) {
          warn(`抓回答出错：${String(error?.message ?? error)}`);
        }
      });
    }

    startPet();
    watchTimer = setInterval(watchTick, WATCH.pollMs);
    if (typeof watchTimer.unref === 'function') watchTimer.unref();
    askTimer = setInterval(pollAsk, 500);
    if (typeof askTimer.unref === 'function') askTimer.unref();
    // SSE 心跳：写失败的连接当场摘掉，别让死连接一直挂着
    sseTimer = setInterval(() => {
      if (sseClients.size === 0) return;
      for (const res of [...sseClients]) {
        try {
          res.write(': ping\n\n');
        } catch {
          sseClients.delete(res);
        }
      }
    }, 15000);
    if (typeof sseTimer.unref === 'function') sseTimer.unref();
    log('就位（桌宠 + pet_say + 看他在哪页 + 问她一句）');
  } catch (error) {
    warn(`注册失败：${String(error?.message ?? error)}`);
  }

  return () => {
    disposed = true;
    if (restartTimer !== null) {
      clearTimeout(restartTimer);
      restartTimer = null;
    }
    if (watchTimer !== null) {
      clearInterval(watchTimer);
      watchTimer = null;
    }
    if (askTimer !== null) {
      clearInterval(askTimer);
      askTimer = null;
    }
    if (ask.timer !== null) {
      clearTimeout(ask.timer);
      ask.timer = null;
    }
    // SSE：先停心跳，再逐个关连接。挂着的连接不关，卸载后就是一堆没人管的
    // 半开 socket；网页那边的 EventSource 还会对着已经不存在的地址重连。
    if (sseTimer !== null) {
      clearInterval(sseTimer);
      sseTimer = null;
    }
    for (const res of [...sseClients]) {
      try {
        res.end(': bye\n\n');
      } catch {
        /* 已经断了就算了 */
      }
    }
    sseClients.clear();
    // 她的短会话也带走：插件卸载后留着它，只会是一条没人管的僵尸会话
    void dropVoice('插件卸载');
    try {
      pet?.kill();
    } catch {
      /* ignore */
    }
    pet = null;
  };
}
