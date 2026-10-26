/**
 * `feiyu-chat-companion` — 浏览器半边：侧栏一项「小肥鱼」+ 一个面板。
 *
 * 契约（照 feiyu-memory 抄的，别自己发明）：
 *   1. 必须调 window.__ModuleLoader__.load({ id, factory })
 *   2. id 必须等于包名
 *   3. factory(require) 返回 { name, inject, apply }
 *
 * 没有打包器，所以全程 React.createElement。UI 只用 --dsw-alias-* 主题 token，
 * 不 import 任何 UI 库 —— 免得别的插件换版本把我们带崩。
 *
 * 面板只做「开关 + 看一眼状态」。真正干活的是 overlay 里那只窗口。
 */
window.__ModuleLoader__.load({
  id: 'feiyu-chat-companion',

  factory: (require) => {
    const React = require('react');
    const h = React.createElement;
    const { useState, useEffect } = React;

    /** 侧栏格子 id，同时也是主面板 key。必须一致。 */
    const PANEL_ID = 'feiyu-chat';
    /** 和 host 半边的 ROUTE_PREFIX 对得上 */
    const API = '/feiyu-chat';

    const C = {
      border1: 'var(--dsw-alias-border-l1)',
      text1: 'var(--dsw-alias-label-primary)',
      text2: 'var(--dsw-alias-label-secondary)',
      brand: 'var(--dsw-alias-brand-primary)',
      layer1: 'var(--dsw-alias-bg-layer-1)',
      idle: 'var(--dsw-alias-state-idle-primary)',
      err: 'var(--dsw-alias-state-error-primary)',
    };

    /* ───────────── 语音（可选：装了 TTS 插件才用得上） ───────────── */

    /**
     * TTS 客户端把自己的设置挂在 window 上（`{ get, save, reset }`），
     * 没装就什么都没有。这是最干净的探测：不用网络、不用问 Host。
     */
    function ttsAvailable() {
      try {
        return typeof window !== 'undefined' && typeof window.__dshTtsSettings?.get === 'function';
      } catch {
        return false;
      }
    }

    /** 把一句话交给 TTS 合成，返回能直接播放的 url。参数照它自己的面板走。 */
    async function ttsUrl(text) {
      let settings;
      try {
        settings = window.__dshTtsSettings.get() || {};
      } catch {
        settings = {};
      }
      const provider = typeof settings.provider === 'string' && settings.provider !== ''
        ? settings.provider
        : 'edge-tts';
      const voice = typeof settings.voice === 'string' && settings.voice !== ''
        ? settings.voice
        : 'zh-CN-XiaoxuanNeural';
      const pct = (v) =>
        typeof v !== 'number' || v === 0 ? 'default' : (v > 0 ? '+' : '') + v + '%';
      const rvc = settings.rvc && typeof settings.rvc === 'object' ? settings.rvc : {};
      const payload = { text, voice, provider };
      if (provider === 'rvc') {
        payload.custom = {
          ...rvc,
          baseRate: pct(rvc.baseRate),
          basePitch: pct(rvc.basePitch),
          baseVolume: pct(rvc.baseVolume),
        };
      } else if (provider === 'index-tts2') {
        const index = settings.index && typeof settings.index === 'object' ? settings.index : {};
        payload.custom = { ...index, voice: index.voice || voice };
      } else if (provider === 'cosyvoice') {
        const cosy = settings.cosy && typeof settings.cosy === 'object' ? settings.cosy : {};
        payload.custom = { ...cosy, voice: cosy.voice || voice };
      } else if (provider === 'google-cloud-tts') {
        const cloudVoice = (settings.cloud && settings.cloud.voice) || voice;
        payload.voice = cloudVoice;
        payload.custom = { voice: cloudVoice };
        payload.prosody = {
          rate: pct(rvc.baseRate),
          pitch: pct(rvc.basePitch),
          volume: pct(rvc.baseVolume),
        };
      } else {
        payload.prosody = {
          rate: pct(rvc.baseRate),
          pitch: pct(rvc.basePitch),
          volume: pct(rvc.baseVolume),
        };
      }
      const response = await fetch('/dsh-tts-api/speak', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!body || typeof body.url !== 'string' || body.url === '') {
        throw new Error(body?.error || `TTS HTTP ${response.status}`);
      }
      return body.url;
    }

    /**
     * 常驻在 shell.overlay 里的小零件：盯着「她刚说了什么」，开了朗读就念。
     *
     * 为什么挂在 overlay 而不是面板里：面板只有点开「肥鱼陪聊」时才存在，
     * 而她是随时会冒话的。声音只能在网页里放，所以网页得开着——桌宠是独立窗口，
     * 关了网页她照样在桌面冒字，只是不出声。
     */
    function Speaker() {
      useEffect(() => {
        let lastSeq = null;
        let stopped = false;
        let audio = null;

        async function tick() {
          if (stopped) return;
          try {
            const data = await api('/state');
            const latest = data?.say;
            if (!latest || typeof latest.seq !== 'number') return;
            // 第一次只看不动：不然一打开页面就把上一句重播一遍
            if (lastSeq === null) {
              lastSeq = latest.seq;
              return;
            }
            if (latest.seq === lastSeq) return;
            lastSeq = latest.seq;
            if (data.speak !== true || !ttsAvailable()) return;
            // Host 明确说这句不念（比如问答提交瞬间那个省略号）
            if (latest.silent === true) return;
            const text = String(latest.text ?? '').trim();
            if (text === '') return;
            const url = await ttsUrl(text);
            if (stopped) return;
            try {
              if (audio) audio.pause();
            } catch {
              /* 旧的那句停了就停了 */
            }
            audio = new Audio(url);
            audio.play().catch(() => {
              /* 浏览器不给自动播就先算了，下一句再说 */
            });
          } catch {
            /* 网络抖一下、没登录，都不该让这个循环停 */
          }
        }

        void tick();
        const timer = setInterval(tick, 1200);
        return () => {
          stopped = true;
          clearInterval(timer);
          try {
            if (audio) audio.pause();
          } catch {
            /* ignore */
          }
        };
      }, []);
      return null;
    }

    /* ───────────── 图标：铁盆 + 两只眼 ───────────── */

    function Icon(props) {
      const size = props && typeof props.size === 'number' ? props.size : 20;
      const active = Boolean(props && props.active);
      return h(
        'svg',
        {
          width: size,
          height: size,
          viewBox: '0 0 24 24',
          fill: 'none',
          role: 'img',
          'aria-label': '小肥鱼',
          style: { display: 'block', opacity: active ? 1 : 0.72 },
        },
        h('path', {
          d: 'M3.5 8.5h17a1 1 0 0 1 1 1v1.2a2.3 2.3 0 0 1-2.3 2.3H4.8A2.3 2.3 0 0 1 2.5 10.7v-1.2a1 1 0 0 1 1-1z',
          stroke: 'currentColor',
          strokeWidth: 1.5,
          strokeLinejoin: 'round',
        }),
        h('circle', { cx: 9.6, cy: 16.4, r: 1.15, fill: 'currentColor' }),
        h('circle', { cx: 14.4, cy: 16.4, r: 1.15, fill: 'currentColor' }),
        h('path', {
          d: 'M9.8 20c1.5 1 3.4 1 4.4 0',
          stroke: 'currentColor',
          strokeWidth: 1.4,
          strokeLinecap: 'round',
        }),
      );
    }

    /* ───────────── 小工具 ───────────── */

    async function api(path, options) {
      const response = await fetch(`${API}${path}`, {
        cache: 'no-store',
        headers: { 'content-type': 'application/json' },
        ...options,
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body?.ok === false) {
        throw new Error(body?.message || `HTTP ${response.status}`);
      }
      return body;
    }

    function Row(props) {
      return h(
        'button',
        {
          type: 'button',
          onClick: props.onClick,
          disabled: props.disabled,
          style: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            width: '100%',
            padding: '10px 13px',
            marginTop: 8,
            cursor: props.disabled ? 'default' : 'pointer',
            opacity: props.disabled ? 0.5 : 1,
            border: `1px solid ${C.border1}`,
            borderRadius: 10,
            background: 'transparent',
            color: C.text1,
            fontSize: 13,
            textAlign: 'left',
            fontFamily: 'inherit',
          },
        },
        h('span', null, props.label),
        h(
          'span',
          { style: { fontSize: 12, color: props.on ? C.brand : C.text2 } },
          props.value,
        ),
      );
    }

    /* ───────────── 主面板 ───────────── */

    function Panel() {
      const [data, setData] = useState(null);
      const [error, setError] = useState('');

      async function refresh() {
        try {
          setData(await api('/state'));
          setError('');
        } catch (e) {
          setError(String(e?.message ?? e));
        }
      }

      useEffect(() => {
        void refresh();
        const timer = setInterval(refresh, 3000);
        return () => clearInterval(timer);
      }, []);

      async function setFlag(flag, value) {
        try {
          await api('/config', { method: 'POST', body: JSON.stringify({ [flag]: value }) });
          await refresh();
        } catch (e) {
          setError(String(e?.message ?? e));
        }
      }

      const running = Boolean(data?.running);
      const muted = Boolean(data?.state?.muted);
      const visible = data?.control?.visible !== false;
      const pos = data?.state;
      const level = data?.level ?? 'low';
      const levels = data?.levels ?? {};
      const length = data?.length ?? 'short';
      const lengths = data?.lengths ?? {};
      const deepRead = data?.deepRead === true;
      const voice = data?.voice ?? {};
      const voiceReady = voice.ready === true;
      const voiceModel = voice?.options?.model ?? '';
      const voiceEffort = voice?.options?.reasoningEffort ?? '';
      const voiceRecycle = voice?.options?.recycleLines ?? 30;
      const speakEnabled = data?.speak === true;
      const tts = ttsAvailable();

      async function setSpeak(next) {
        try {
          await api('/config', { method: 'POST', body: JSON.stringify({ speak: next }) });
          await refresh();
        } catch (e) {
          setError(String(e?.message ?? e));
        }
      }

      async function recycleVoice() {
        try {
          await api('/voice', { method: 'POST', body: JSON.stringify({ recycle: true }) });
          await refresh();
        } catch (e) {
          setError(String(e?.message ?? e));
        }
      }

      async function setLevel(next) {
        try {
          await api('/config', { method: 'POST', body: JSON.stringify({ level: next }) });
          await refresh();
        } catch (e) {
          setError(String(e?.message ?? e));
        }
      }

      async function setLength(next) {
        try {
          await api('/config', { method: 'POST', body: JSON.stringify({ length: next }) });
          await refresh();
        } catch (e) {
          setError(String(e?.message ?? e));
        }
      }

      async function setDeepRead(next) {
        try {
          await api('/config', { method: 'POST', body: JSON.stringify({ deepRead: next }) });
          await refresh();
        } catch (e) {
          setError(String(e?.message ?? e));
        }
      }

      return h(
        'div',
        // 外层负责滚。宿主给的高度是固定的，内容比它高就必须自己滚，
        // 不然加两行设置就顶出可视区、谁也够不着（照 feiyu-memory 的写法）。
        { style: { height: '100%', overflowY: 'auto', color: C.text1 } },
        h(
          'div',
          { style: { maxWidth: 560, margin: '0 auto', padding: '20px 20px 56px' } },

        h('h2', { style: { margin: '0 0 4px', fontSize: 17, fontWeight: 600 } }, '小肥鱼'),
        h(
          'p',
          { style: { margin: '0 0 18px', fontSize: 12, color: C.text2, lineHeight: 1.7 } },
          '她一直待在桌面上，能拖、会眨眼。这里管她说什么、露不露面。挂到重启 DSH 后第一个对话的窗口。',
        ),

        h(
          'div',
          {
            style: {
              display: 'flex',
              gap: 14,
              alignItems: 'center',
              padding: '10px 13px',
              borderRadius: 10,
              background: C.layer1,
              fontSize: 12,
              color: C.text2,
            },
          },
          h('span', {
            style: {
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: running ? C.brand : C.idle,
            },
          }),
          h('span', null, running ? '在桌面上' : '没跑起来'),
          pos && typeof pos.x === 'number'
            ? h('span', null, `位置 ${pos.x}, ${pos.y}`)
            : null,
        ),

        h(
          'div',
          { style: { marginTop: 10, padding: '10px 13px', borderRadius: 10, background: C.layer1, fontSize: 12, color: C.text2, lineHeight: 1.7 } },
          h(
            'div',
            null,
            voiceReady
              ? `回话走她自己的短会话 · 说过 ${voice.lines ?? 0} 句 · ${voiceModel} / 思考 ${voiceEffort}`
              : '短会话还没建（第一次开口时建）；现在这句会借用你正在用的会话',
          ),
          voiceReady
            ? null
            : voice.lastError
              ? h(
                  'div',
                  { style: { marginTop: 4, color: C.err, wordBreak: 'break-all', fontWeight: 600 } },
                  String(voice.lastError),
                )
              : null,
          h(
            'div',
            { style: { marginTop: 4 } },
            `攒够 ${voiceRecycle} 句就换一条新的，免得它自己长回去。`,
          ),
        ),
        h(Row, {
          label: '换一条短会话',
          value: voiceReady ? '丢掉现在这条' : '现在建一条',
          on: false,
          disabled: false,
          onClick: () => void recycleVoice(),
        }),

        h(Row, {
          label: running ? '关掉' : '启动',
          value: running ? '让进程退出' : '把桌宠叫出来',
          on: false,
          disabled: false,
          onClick: () => void setFlag(running ? 'stop' : 'start', true),
        }),
        h(Row, {
          label: '显示',
          value: visible ? '露着' : '藏着',
          on: visible,
          disabled: !running,
          onClick: () => void setFlag('visible', !visible),
        }),
        h(Row, {
          label: '说话',
          value: muted ? '已暂停' : '会出声',
          on: !muted,
          disabled: !running,
          onClick: () => void setFlag('muted', !muted),
        }),
        h(Row, {
          label: '归位',
          value: '挪回右下角',
          on: false,
          disabled: !running,
          onClick: () => void setFlag('center', true),
        }),

        h(
          'div',
          { style: { marginTop: 20, fontSize: 12, color: C.text2 } },
          '说话频率',
        ),
        h(
          'div',
          { style: { display: 'flex', gap: 8, marginTop: 8 } },
          Object.keys(levels).map((key) =>
            h(
              'button',
              {
                key,
                type: 'button',
                onClick: () => void setLevel(key),
                style: {
                  flex: 1,
                  padding: '9px 0',
                  borderRadius: 9,
                  border: `1px solid ${key === level ? C.brand : C.border1}`,
                  background: key === level ? 'rgba(80,140,220,0.15)' : 'transparent',
                  color: key === level ? C.brand : C.text2,
                  fontSize: 12,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                },
              },
              `${levels[key].label} · ${levels[key].hint}`,
            ),
          ),
        ),

        h(
          'div',
          { style: { marginTop: 20, fontSize: 12, color: C.text2 } },
          '回话长度',
        ),
        h(
          'div',
          { style: { display: 'flex', gap: 8, marginTop: 8 } },
          Object.keys(lengths).map((key) =>
            h(
              'button',
              {
                key,
                type: 'button',
                onClick: () => void setLength(key),
                style: {
                  flex: 1,
                  padding: '9px 0',
                  borderRadius: 9,
                  border: `1px solid ${key === length ? C.brand : C.border1}`,
                  background: key === length ? 'rgba(80,140,220,0.15)' : 'transparent',
                  color: key === length ? C.brand : C.text2,
                  fontSize: 12,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                },
              },
              `${lengths[key].label} · ${lengths[key].hint}`,
            ),
          ),
        ),
        h(
          'p',
          { style: { margin: '8px 0 0', fontSize: 11.5, color: C.err, lineHeight: 1.7, fontWeight: 600 } },
          '很贵！长回答大约是短回答的二十倍消耗。',
        ),

        h(
          'div',
          { style: { marginTop: 20, fontSize: 12, color: C.text2 } },
          '看什么',
        ),
        h(
          'div',
          { style: { display: 'flex', gap: 8, marginTop: 8 } },
          [
            { key: false, label: '只看标题' },
            { key: true, label: '标题 + B站内容' },
          ].map((item) =>
            h(
              'button',
              {
                key: String(item.key),
                type: 'button',
                onClick: () => void setDeepRead(item.key),
                style: {
                  flex: 1,
                  padding: '9px 0',
                  borderRadius: 9,
                  border: `1px solid ${item.key === deepRead ? C.brand : C.border1}`,
                  background: item.key === deepRead ? 'rgba(80,140,220,0.15)' : 'transparent',
                  color: item.key === deepRead ? C.brand : C.text2,
                  fontSize: 12,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                },
              },
              item.label,
            ),
          ),
        ),
        h(
          'p',
          { style: { margin: '8px 0 0', fontSize: 11.5, color: C.text2, lineHeight: 1.7 } },
          '选「标题 + B站内容」后，看 B站 视频时我会去翻字幕和评论，说的话更贴内容，也稍微贵一点。',
        ),

        // 只在装了 TTS 插件时出现。没装就整行都不渲染 ——
        // 渲染成灰按钮的话，用户会以为它坏了。
        tts
          ? h(
              'div',
              { style: { marginTop: 20, fontSize: 12, color: C.text2 } },
              '念出来',
            )
          : null,
        tts
          ? h(Row, {
              label: '朗读',
              value: speakEnabled ? '会念出声' : '只冒气泡',
              on: speakEnabled,
              disabled: false,
              onClick: () => void setSpeak(!speakEnabled),
            })
          : null,
        tts
          ? h(
              'p',
              { style: { margin: '8px 0 0', fontSize: 11.5, color: C.text2, lineHeight: 1.7 } },
              '用的是「语音」插件里选的音色和引擎。声音在网页里放，所以网页关掉就只剩气泡没声音。',
            )
          : null,

        h(
          'p',
          { style: { margin: '18px 0 0', fontSize: 11.5, color: C.text2, lineHeight: 1.7 } },
          '右键点她也能开同一个菜单。',
        ),

        error
          ? h('p', { style: { margin: '12px 0 0', fontSize: 12, color: C.err } }, error)
          : null,
        ),
      );
    }

    /* ───────────── 注册 ───────────── */

    function apply(ctx) {
      // order 41：紧跟在「肥鱼日记」(40) 后面
      ctx.slots.inject('sidebar.panellist', () =>
        ctx.slots.register(
          { name: 'sidebar.panellist', id: PANEL_ID, order: 41, label: () => '肥鱼陪聊' },
          Icon,
        ),
      );
      ctx.slots.inject('main', () =>
        ctx.slots.register({ name: 'main', key: PANEL_ID }, Panel),
      );
      // 常驻的「念」：不占地方，只在有 TTS 时装个轮询。
      // order 靠后，别跟 TTS 自己的 overlay 抢位。
      ctx.slots.inject('shell.overlay', () =>
        ctx.slots.register(
          { name: 'shell.overlay', key: 'feiyu-chat-speaker', id: 'feiyu-chat-speaker', order: 1010 },
          Speaker,
        ),
      );
    }

    return { name: 'feiyu-chat-companion', inject: ['slots'], apply };
  },
});
