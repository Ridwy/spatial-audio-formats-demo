#!/bin/bash
# 聴講者に配る一式を demo/synth/dist/ に作る (GitHub にそのまま置ける自己完結フォルダ)。
#   binaural/  HRTF 済みステレオ WAV (どの端末でも。OS の空間化はオフで聴く)
#   apac/      APAC (5.1 / FOA / 3次)。Apple 端末 + AirPods でヘッドトラッキング付きのレンダリング
#   both/      APAC + AAC ステレオ fallback を 1 ファイルに持つ (iPhone の撮影ファイルと同じ構造)
# 前提: encode.py → render_binaural.swift → make_listening_page.py を済ませてあること。
set -euo pipefail
cd "$(dirname "$0")"
DIST=dist
mkdir -p $DIST/binaural $DIST/apac $DIST/both out/apac out/both

echo "== binaural (ラウドネス揃え済みの out/listen をコピー)"
for f in object ch51 foa hoa3; do cp out/listen/$f.wav $DIST/binaural/$f.wav; done

echo "== APAC"
for f in ch51 foa hoa3; do
  case $f in
    ch51) layout=MPEG_5_1_A; rate=384000 ;;   # 5.1 (L R C LFE Ls Rs)
    foa)  layout=0xBE0004;   rate=384000 ;;   # HOA_ACN_SN3D | 4ch
    hoa3) layout=0xBE0010;   rate=768000 ;;   # HOA_ACN_SN3D | 16ch
  esac
  afconvert out/$f.wav out/apac/${f}_pcm.caf -f caff -d LEI24 -l $layout
  afconvert out/apac/${f}_pcm.caf out/apac/$f.mp4 -f mp4f -d apac -l $layout -b $rate -u csrc 39 -u cdrc 3 -u aspf 75
  cp out/apac/$f.mp4 $DIST/apac/$f.mp4
  afinfo $DIST/apac/$f.mp4 | grep -E "Data format|bit rate" | tr '\n' ' '; echo
done

echo "== both (APAC + AAC fallback)"
for f in ch51 foa hoa3; do
  swift mux_fallback.swift out/apac/$f.mp4 out/listen/$f.wav out/both/$f.mov
  cp out/both/$f.mov $DIST/both/$f.mov
done

echo "== page"
python3 make_dist_page.py
du -sh $DIST; ls -la $DIST/*/
