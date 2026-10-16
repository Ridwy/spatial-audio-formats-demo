#!/usr/bin/env python3
"""配布用ページ demo/synth/dist/index.html を作る (build_dist.sh から呼ばれる)。"""
from pathlib import Path

DIST = Path(__file__).resolve().parent / "dist"
FORMATS = [  # 並び順は Channel → Object → Scene (1 次 → 3 次)
    ("ch51", "Channel 5.1", "スピーカー 5 本の音をそのまま保存。音像はスピーカー間の中間に作られる", True),
    ("object", "Object", "モノ 1 本 + 位置の列。再生時に位置へ置く", False),
    ("foa", "Scene FOA (1次)", "4 本の係数 (W, Y, Z, X)。1 次はにじむ", True),
    ("hoa3", "Scene 3次", "16 本の係数。1 次より締まる", True),
]

bin_btns = "".join(f'<button data-k="{k}"><b>{l}</b><br><small>{d}</small></button>' for k, l, d, _ in FORMATS)
bin_auds = "".join(f'<audio preload="auto" data-k="{k}" src="binaural/{k}.wav"></audio>' for k, _, _, _ in FORMATS)
apac_rows = "".join(
    (f'<tr><td><b>{l}</b></td><td><audio controls preload="none" src="apac/{k}.mp4"></audio></td>'
     f'<td><a href="apac/{k}.mp4" download>apac/{k}.mp4</a></td><td><a href="both/{k}.mov" download>both/{k}.mov</a></td></tr>')
    if has else
    f'<tr><td><b>{l}</b></td><td colspan="3"><small>無し。Apple のエンコーダ (afconvert / AVAssetWriter) が APAC に書けるのは 3 次までの Ambisonics とチャンネルベースだけで、Object の ASAF / APAC 化はプロツール (Pro Tools, Resolve) 側の役目。A のバイノーラル版で聴く</small></td></tr>'
    for k, l, _, has in FORMATS)

html = f"""<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>同じ点音源を 3 通りに記録して聴き比べ</title><style>
body{{font-family:-apple-system,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;line-height:1.6}}
section{{border:1px solid #ccc;border-radius:10px;padding:12px 16px;margin:16px 0}}
.btns button{{display:block;width:100%;text-align:left;margin:6px 0;padding:8px;border-radius:6px;border:1px solid #999;background:#f6f6f6}}
.btns button.on{{background:#ef5237;color:#fff;border-color:#ef5237}}.ctl{{margin-top:8px}}
table{{border-collapse:collapse;width:100%}}td{{border-top:1px solid #ddd;padding:6px 4px;vertical-align:middle}}audio{{width:100%;max-width:260px}}
.note{{background:#fff5f2;border-left:4px solid #ef5237;padding:8px 12px}}
</style>
<h1>同じ点音源を 3 通りに記録して聴き比べ</h1>
<p>音源は「ぜろ〜じゅういち」を 1 秒おきに数えながら、1.5 m の距離で<b>時計回りに 1 周</b>する。
数字は<b>時計の文字盤の位置</b> (ぜろ = 12 時 = 正面, さん = 3 時 = 右, ろく = 6 時 = 後ろ, きゅう = 9 時 = 左)。
同じ音源・同じ軌道を Channel / Object / Scene の 3 通りで記録してある。違いは「記録の仕方」だけ。</p>

<section><h2>A. バイノーラル版 (どの端末でも)</h2>
<p class="note">ヘッドホンで。<b>OS の「空間オーディオ / ステレオを空間化」はオフ</b> (すでに HRTF 済みなので、オンだと二重にかかる)。</p>
<p>4 形式とも AVAudioEnvironmentNode (Apple の HRTF) で同じようにレンダリング済み。ボタンで<b>同じ再生位置のまま</b>切り替わる。ラウドネスは揃えてある。</p>
<div class="btns">{bin_btns}</div>
<div class="ctl"><button class="play">▶ 再生 / 一時停止</button> <span class="t">0.0 s</span></div>{bin_auds}
</section>

<section><h2>B. APAC 版 (iPhone / iPad / Mac + AirPods など)</h2>
<p class="note">こちらは逆に<b>空間オーディオをオン</b> (ヘッドトラッキングも可)。端末側のレンダラーが 5.1 / FOA / 3 次をそのまま受け取って頭の向きに合わせて鳴らす。</p>
<p>Apple Positional Audio Codec (APAC) で符号化した素のデータ。再生できない環境では無音か再生不可になる。<code>both/</code> は iPhone の撮影ファイルと同じ構造で、<b>APAC トラック (無効) + AAC ステレオ (有効, fallback)</b> の 2 本を 1 ファイルに持つ。AAC 側の中身は A のバイノーラル。</p>
<table><tr><td></td><td>再生 (APAC)</td><td>APAC のみ</td><td>APAC + fallback</td></tr>{apac_rows}</table>
</section>

<section><h2>何を聴くか</h2>
<ul>
<li><b>Channel 5.1</b>: 2〜4 時がどれも「右」で区別がつきにくく、楕円に感じる。R と Rs の間 80° はファントム音像。6 時 (Ls/Rs の中間) はちゃんと後ろ。</li>
<li><b>Object</b>: 定位がいちばんはっきりする。</li>
<li><b>Scene FOA</b>: 方向は Object とほぼ同じだが、よく聞くとふわっとしている (1 次のにじみ)。</li>
<li><b>Scene 3 次</b>: FOA より締まって Object に近づく。</li>
</ul>
</section>
<script>
document.querySelectorAll('section').forEach(s=>{{
  const auds=[...s.querySelectorAll('audio[data-k]')], btns=[...s.querySelectorAll('.btns button')], t=s.querySelector('.t');
  if(!auds.length) return;
  let cur=auds[0]; const mark=()=>btns.forEach(b=>b.classList.toggle('on',b.dataset.k===cur.dataset.k)); mark();
  btns.forEach(b=>b.onclick=()=>{{const nx=auds.find(a=>a.dataset.k===b.dataset.k), playing=!cur.paused;
    nx.currentTime=cur.currentTime; cur.pause(); cur=nx; if(playing) cur.play(); mark();}});
  s.querySelector('.play').onclick=()=>{{document.querySelectorAll('audio').forEach(a=>{{if(a!==cur)a.pause()}}); cur.paused?cur.play():cur.pause();}};
  auds.forEach(a=>a.ontimeupdate=()=>{{if(a===cur)t.textContent=a.currentTime.toFixed(1)+' s'}});
}});
</script></html>"""
(DIST / "index.html").write_text(html)
print("wrote", DIST / "index.html")
