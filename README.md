# 同じ点音源を Channel / Object / Scene の 3 通りに記録して聴き比べる

CA.swift #23 の発表「続・空間オーディオを活用しよう！」のデモ素材。
音源・軌道・レンダラーを全部そろえて、差が「記録の仕方」だけになるようにしてある。

**聴き比べページ: https://ridwy.github.io/spatial-audio-formats-demo/dist/**

音源は「ぜろ〜じゅういち」を 1 秒おきに数えながら、1.5 m の距離で時計回りに 1 周する。
数字は時計の文字盤の位置 (ぜろ = 12 時 = 正面, さん = 3 時 = 右, ろく = 6 時 = 後ろ, きゅう = 9 時 = 左)。

## 配布ファイル (`dist/`)

| フォルダ | 中身 | 聴き方 |
|---|---|---|
| `binaural/*.wav` | 4 形式 (Object / 5.1 / FOA / 3 次) を Apple の HRTF (AVAudioEnvironmentNode) で同じようにバイノーラル化したステレオ | どの端末でも。ヘッドホンで、**OS の「空間オーディオ / ステレオを空間化」はオフ** (すでに HRTF 済みなので二重にかかる) |
| `apac/*.mp4` | 5.1 / FOA / 3 次を Apple Positional Audio Codec (APAC) にした素のデータ | Apple 端末 + AirPods などで**空間オーディオをオン**。端末側がヘッドトラッキング付きでレンダリングする。Object は afconvert の APAC では書けないので無し (Object を運ぶのは ASAF) |
| `both/*.mov` | APAC トラック (無効) + AAC ステレオ (有効, fallback 参照, alternate group) を 1 ファイルに持つ、iPhone の空間オーディオ撮影ファイルと同じ構造。AAC 側はバイノーラル | APAC を再生できる環境では APAC、できなければ AAC が鳴る |

## 聴きどころ

- **Channel 5.1**: 2〜4 時がどれも「右」で区別がつきにくく、楕円に感じる。R と Rs の間 80° はファントム音像。6 時 (Ls/Rs の中間) はちゃんと後ろ。
- **Object**: 定位がいちばんはっきりする。
- **Scene FOA (1 次)**: 方向は Object とほぼ同じだが、よく聞くとふわっとしている。
- **Scene 3 次**: FOA より締まって Object に近づく。

2〜8 kHz の左右レベル差 (ILD) と到達時間差 (ITD) を 1 秒ごとに測ると、右真横 (さん, 3〜4 s) で

| | ILD | ITD |
|---|---|---|
| Object | −13 dB | 0.83 ms |
| Channel 5.1 | −12 dB | 0.77 ms |
| FOA | −12 dB | 0.63 ms |
| 3 次 | −13 dB | 0.77 ms |

FOA だけ ITD が小さく、1 次のにじみが数字にも出ている。後ろ (ろく, 6 s) は全形式で ILD ≈ 0。

## 作り方 (macOS, Python 3 + numpy/scipy, Swift)

```bash
python3 encode.py                                   # 音源 + 3 形式のエンコード → out/
for s in object ch51 foa hoa3; do
  swift render_binaural.swift out/spec_$s.json out/bin_$s.wav
done
python3 make_listening_page.py                      # ラウドネス揃え → out/listen/
./build_dist.sh                                     # APAC / both / 配布ページ → dist/
```

- 音源: `say -v Kyoko` の読み上げ + 各秒頭に小さなクリック。
- Channel: ITU 5.1 (L/R ±30°, C, Ls/Rs ±110°) に 2D VBAP でパン。LFE は空。
- Object: モノ 1 本 + 10 ms おきの位置列 (`trajectory.json`)。
- Scene: AmbiX (ACN/SN3D) の 1 次 (4ch) と 3 次 (16ch)。球面調和関数は `ambi.py`。
- レンダラー `render_binaural.swift`: AVAudioEngine のオフラインレンダリングで AVAudioEnvironmentNode (HRTFHQ, 残響なし, 1.5 m で 0 dB)。
  - Object はプレイヤーノードの position を 10 ms ごとに更新。
  - Channel はスピーカー位置に固定した 5 本の仮想音源。
  - Scene は環境ノードが Ambisonics を直接受けないので、水平リング 8 本の仮想スピーカーに mode-matching (セクトラル成分のみ, 2D max-rE 重み) でデコードしてから 8 本の仮想音源として渡す。
  - 第 3 引数 yaw (度) で「聴き手が左を向いた」結果も出せる。
- APAC: `afconvert ... -d apac -l <layout> -u csrc 39 -u cdrc 3 -u aspf 75` (Apple の APAC ドキュメントの例と同じ指定)。
- `mux_fallback.swift`: APAC をパススルーで取り込み、ステレオを AAC にして、`marksOutputTrackAsEnabled = false` + `.audioFallback` 関連付け + `AVAssetWriterInputGroup` で iPhone と同じ alternate group 構造にする。入力は先に個別に `add` してからグループを `add` する (グループだけだと `isReadyForMoreMediaData` が true にならない)。

`encode.py two` で 2 時と 4 時に別の声を同時に置く版も作れる (差が分かりにくかったので配布には入れていない)。

## 既知の限界

- 会場スピーカーではバイノーラルの外部化は効かないので、手元のヘッドホンで聴く前提。
- Channel の「後ろ」は Ls/Rs の 140° 開きの中間に作る音像なので弱い。これは形式の性質そのもの。
- Kyoko の素は 22.05 kHz なので声の帯域は 11 kHz まで。
- iPhone + AirPods で `apac/*.mp4` と `both/*.mov` がヘッドトラッキング付きで鳴るかは未確認。
