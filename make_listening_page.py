#!/usr/bin/env python3
"""render_binaural.swift の出力をラウドネス (-20 LUFS 目安) で揃え、同じ再生位置のまま切り替えて聴けるページを作る。

    python3 demo/synth/make_listening_page.py
出力: demo/synth/out/listen/*.wav, demo/synth/out/listen/index.html
"""
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

OUT = Path(__file__).resolve().parent / "out"
DST = OUT / "listen"
DST.mkdir(exist_ok=True)
TARGET = -23.0  # -20 だとピークが 0.99 に当たる
K1 = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
K2 = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])

FORMATS = [
    ("ch51", "Channel 5.1", "スピーカー 5 本の音をそのまま保存 (6 本の波形)。音像はスピーカー間の中間に作られる"),
    ("object", "Object", "モノ 1 本 + 位置の列。再生時に位置へ置く"),
    ("foa", "Scene FOA (1次)", "4 本の係数 (W, Y, Z, X)。回転は行列 1 つ。1 次はにじむ"),
    ("hoa3", "Scene 3次", "16 本の係数。1 次より締まる"),
]
# 2026-10-15 聴いた結果: 「1 周・正面」だけで十分 (左 90° 向きと 2 本同時は差が分かりにくい)。残りは必要なら戻す。
VIEWS = [("", "", "1 周: 正面を向いて聴く")]
# VIEWS += [("", "_yaw90", "1 周: 左 90° を向いて聴く"),
#           ("two_", "", "2 本同時: 2 時に女声 (数字)、4 時に男声 (かな)。分かれて聞こえるか")]


def lufs(x):
    y = lfilter(*K2, lfilter(*K1, x, axis=0), axis=0)
    return -0.691 + 10 * np.log10((y**2).mean(0).sum() + 1e-20)


sections = []
for prefix, suffix, vlabel in VIEWS:
    btns, auds = [], []
    for key, label, desc in FORMATS:
        if not (OUT / f"bin_{prefix}{key}{suffix}.wav").exists():
            continue
        sr, x = wavfile.read(OUT / f"bin_{prefix}{key}{suffix}.wav")
        x = x.astype(np.float64)
        g = 10 ** ((TARGET - lufs(x)) / 20)
        y = np.clip(x * g, -0.99, 0.99)
        name = f"{prefix}{key}{suffix}.wav"
        wavfile.write(DST / name, sr, (y * 32767).astype(np.int16))
        print(f"{name:18s} {lufs(x):6.1f} → {lufs(y):6.1f} LUFS  peak {np.abs(y).max():.2f}")
        btns.append(f'<button data-k="{key}"><b>{label}</b><br><small>{desc}</small></button>')
        auds.append(f'<audio preload="auto" data-k="{key}" src="{name}"></audio>')
    if not btns:
        continue
    sections.append(
        f'<section><h2>{vlabel}</h2><div class="btns">{"".join(btns)}</div>'
        f'<div class="ctl"><button class="play">▶ 再生 / 一時停止</button> <span class="t">0.0 s</span></div>{"".join(auds)}</section>')

html = f"""<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>同じ点音源を Channel / Object / Scene で記録して聴き比べ</title><style>
body{{font-family:-apple-system,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;line-height:1.6}}
section{{border:1px solid #ccc;border-radius:10px;padding:12px 16px;margin:16px 0}}
.btns button{{display:block;width:100%;text-align:left;margin:6px 0;padding:8px;border-radius:6px;border:1px solid #999;background:#f6f6f6}}
.btns button.on{{background:#ef5237;color:#fff;border-color:#ef5237}}.ctl{{margin-top:8px}}
</style><h1>同じ点音源を Channel / Object / Scene で記録して聴き比べ</h1>
<p><b>ヘッドホンで、OS の「空間オーディオ / ステレオを空間化」をオフにして</b> (すでに HRTF 済みなので、オンだと二重にかかる)。音源は「ぜろ〜じゅういち」を 1 秒おきに数えながら、1.5 m の距離で<b>時計回りに 1 周</b>する。
数字は<b>時計の文字盤の位置</b> (ぜろ = 12 時 = 正面, さん = 3 時 = 右, ろく = 6 時 = 後ろ, きゅう = 9 時 = 左)。全部 AVAudioEnvironmentNode (Apple の HRTF) で同じようにレンダリング。
ボタンを押すと<b>同じ再生位置のまま</b>切り替わる。ラウドネスは {TARGET:.0f} LUFS に揃えてある。</p>
{"".join(sections)}
<script>
document.querySelectorAll('section').forEach(s=>{{
  const auds=[...s.querySelectorAll('audio')], btns=[...s.querySelectorAll('.btns button')], t=s.querySelector('.t');
  let cur=auds[1]; const mark=()=>btns.forEach(b=>b.classList.toggle('on',b.dataset.k===cur.dataset.k)); mark();
  btns.forEach(b=>b.onclick=()=>{{const nx=auds.find(a=>a.dataset.k===b.dataset.k), playing=!cur.paused;
    nx.currentTime=cur.currentTime; cur.pause(); cur=nx; if(playing) cur.play(); mark();}});
  s.querySelector('.play').onclick=()=>{{document.querySelectorAll('audio').forEach(a=>{{if(a!==cur)a.pause()}}); cur.paused?cur.play():cur.pause();}};
  auds.forEach(a=>a.ontimeupdate=()=>{{if(a===cur)t.textContent=a.currentTime.toFixed(1)+' s'}});
}});
</script></html>"""
(DST / "index.html").write_text(html)
print("wrote", DST / "index.html")
