#!/usr/bin/env python3
"""同じ点音源を Channel / Object / Scene の 3 通りに記録する (合成デモの素材生成)。

音源: 「ぜろ〜じゅういち」を 1 秒おきに読み上げ (say -v Kyoko) + 各秒頭に小さなクリック。
軌道: 聴き手の周りを 1.5 m の距離で時計回りに 1 周 (正面 → 右 → 後ろ → 左 → 正面)。12 秒。
      数字 = 時計の文字盤の位置: 「ぜろ」= 正面 (12 時), 「さん」= 右 (3 時), 「ろく」= 後ろ (6 時), 「きゅう」= 左 (9 時)。

出力 (out/):
  src.wav              モノ音源 (Object 用)
  trajectory.json      Object 用の位置列 (10 ms おき)
  ch51.wav             Channel: 5.1 (L R C LFE Ls Rs) に 2D VBAP でパン
  foa.wav              Scene: 1 次 AmbiX (ACN/SN3D, W Y Z X)
  hoa3.wav             Scene: 3 次 AmbiX (16ch)
  foa_ring8.wav        foa.wav を仮想スピーカー 8 本 (水平リング) にデコードしたもの
  hoa3_ring8.wav       hoa3.wav を同じく
  spec_*.json          render_binaural.swift に渡すレンダリング指定

方位は AmbiX 流 (正面 0°, 左 +90°, 右 −90°, 後ろ 180°)。
    python3 encode.py          # 1 音源が 1 周
    python3 encode.py two      # 2 時 (女声・数字) と 4 時 (男声・かな) の 2 本同時 → two_*
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ambi import real_sh, acn_nm  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
SR = 48000
DUR = 12.0
DIST = 1.5
WORDS = ["ぜろ", "いち", "に", "さん", "よん", "ご", "ろく", "なな", "はち", "きゅう", "じゅう", "じゅういち"]
RING_N = 8  # 仮想スピーカー本数 (水平リング)
ITU51 = {"L": 30, "R": -30, "C": 0, "Ls": 110, "Rs": -110}  # 度, AmbiX 方位 (左 +)


# ---------------------------------------------------------------- 音源
def synth_word(word, path, voice="Kyoko"):
    subprocess.run(["say", "-v", voice, "-o", str(path), "--file-format=WAVE",
                    f"--data-format=LEI16@{SR}", word], check=True)
    sr, x = wavfile.read(path)
    assert sr == SR
    x = x.astype(np.float64) / 32768.0
    # 前後の無音を詰める
    idx = np.where(np.abs(x) > 1e-3)[0]
    return x[max(idx[0] - 240, 0): idx[-1] + 480]


def make_source(words_list=WORDS, voice="Kyoko", tag=""):
    n = int(SR * (DUR + 0.5))
    src = np.zeros(n)
    t = np.arange(n) / SR
    tmp = OUT / f"words{tag}"
    tmp.mkdir(exist_ok=True)
    rms = []
    words = [synth_word(w, tmp / f"{i:02d}.wav", voice) for i, w in enumerate(words_list)]
    for i, w in enumerate(words):
        rms.append(np.sqrt((w**2).mean()))
    ref = np.median(rms)
    for i, w in enumerate(words):
        w = w * (ref / rms[i])
        i0 = int((i + 0.12) * SR)  # クリックの 120 ms 後に発話
        src[i0:i0 + len(w)] += w
    # 各秒頭に短いクリック (定位の手がかり用、小さめ)
    click_len = int(0.004 * SR)
    click = np.hanning(click_len) * np.sin(2 * np.pi * 2500 * np.arange(click_len) / SR)
    for i in range(len(words_list)):
        i0 = int(i * SR)
        src[i0:i0 + click_len] += 0.25 * click
    src /= np.abs(src).max() / 0.7
    return src, t


# ---------------------------------------------------------------- 軌道
def trajectory(t):
    az = -2 * np.pi * np.clip(t / DUR, 0, 1)  # 時計回り (右へ)
    el = np.zeros_like(t)
    return az, el


# ---------------------------------------------------------------- Channel (2D VBAP, 5.1)
def vbap2d_gains(az, spk_deg):
    """水平面の pairwise VBAP。az: (n,), 戻り値 (n, len(spk))。"""
    spk = np.deg2rad(np.array(spk_deg, dtype=float))
    order = np.argsort(spk)
    spk_sorted = spk[order]
    g = np.zeros((az.size, spk.size))
    az = (az + np.pi) % (2 * np.pi) - np.pi
    for k in range(spk.size):
        a, b = spk_sorted[k], spk_sorted[(k + 1) % spk.size]
        ia, ib = order[k], order[(k + 1) % spk.size]
        if (k + 1) == spk.size:  # 最後のペアは 2π をまたぐ
            b = b + 2 * np.pi
            azk = np.where(az < a, az + 2 * np.pi, az)
        else:
            azk = az
        sel = (azk >= a) & (azk <= b)
        if not sel.any():
            continue
        ua, ub = np.array([np.cos(a), np.sin(a)]), np.array([np.cos(b), np.sin(b)])
        L = np.stack([ua, ub], 1)  # 2x2
        p = np.stack([np.cos(azk[sel]), np.sin(azk[sel])], 1)  # (m,2)
        gg = np.linalg.solve(L, p.T).T  # (m,2)
        gg = np.clip(gg, 0, None)
        gg /= np.linalg.norm(gg, axis=1, keepdims=True) + 1e-12
        g[sel, ia] += gg[:, 0]
        g[sel, ib] += gg[:, 1]
    return g


# ---------------------------------------------------------------- Scene (AmbiX) と仮想スピーカーデコード
def ambix_encode(src, az, el, N):
    Y = real_sh(N, az, el, norm="sn3d")  # (n, K)
    return src[:, None] * Y


def ring_decoder(N, ring_az):
    """水平リング用 mode-matching デコーダ。セクトラル成分 (|m| = n) だけを使う。"""
    nm = acn_nm(N)
    sect = [i for i, (n, m) in enumerate(nm) if abs(m) == n]
    Yr = real_sh(N, ring_az, np.zeros_like(ring_az), norm="sn3d")[:, sect]  # (S, Ks)
    D = np.linalg.pinv(Yr.T)  # (S, Ks): g = D @ b_sect
    # 2D max-rE 重み (次数ごと)
    w = np.array([np.cos(nm[i][0] * np.pi / (2 * N + 2)) for i in sect])
    # 正面の平面波をデコードしたときの電力和が 1 になるよう正規化
    b0 = real_sh(N, 0.0, 0.0, norm="sn3d")[0, sect] * w
    g0 = D @ b0
    D /= np.sqrt((g0**2).sum())
    return sect, w, D


def ring_decode(ambi, N, ring_az):
    sect, w, D = ring_decoder(N, ring_az)
    return (ambi[:, sect] * w) @ D.T  # (n, S)


# ---------------------------------------------------------------- 出力
def write(name, x):
    x = np.asarray(x, dtype=np.float32)
    wavfile.write(OUT / name, SR, x)
    print(f"  {name:18s} {x.shape[1] if x.ndim > 1 else 1:2d}ch  peak {np.abs(x).max():.3f}")


def spec(name, sources, note):
    j = {"sampleRate": SR, "distance": DIST, "note": note, "sources": sources}
    (OUT / f"spec_{name}.json").write_text(json.dumps(j, ensure_ascii=False, indent=1))


def main():
    print("source")
    src, t = make_source()
    az, el = trajectory(t)
    write("src.wav", src)
    step = int(0.01 * SR)
    traj = [[round(float(t[i]), 3), round(float(np.degrees(az[i])), 2), 0.0, DIST] for i in range(0, len(t), step)]
    (OUT / "trajectory.json").write_text(json.dumps(traj))
    spec("object", [{"file": "src.wav", "channel": 0, "trajectory": "trajectory.json"}],
         "Object: モノ 1 本 + 位置列。レンダラーが HRTF で位置に置く")

    print("channel 5.1")
    names = ["L", "R", "C", "Ls", "Rs"]
    g = vbap2d_gains(az, [ITU51[k] for k in names])
    ch = np.zeros((len(src), 6))
    for i, k in enumerate(names):
        ch[:, {"L": 0, "R": 1, "C": 2, "Ls": 4, "Rs": 5}[k]] = src * g[:, i]
    write("ch51.wav", ch)
    spec("ch51", [{"file": "ch51.wav", "channel": {"L": 0, "R": 1, "C": 2, "Ls": 4, "Rs": 5}[k],
                   "az": ITU51[k], "el": 0.0, "label": k} for k in names],
         "Channel 5.1: スピーカー 5 本を仮想音源として HRTF で置く (LFE は無し)")

    ring_az = np.deg2rad(np.arange(RING_N) * 360.0 / RING_N)
    for N, name in [(1, "foa"), (3, "hoa3")]:
        print(f"scene order {N}")
        ambi = ambix_encode(src, az, el, N)
        write(f"{name}.wav", ambi)
        ring = ring_decode(ambi, N, ring_az)
        write(f"{name}_ring8.wav", ring)
        spec(name, [{"file": f"{name}_ring8.wav", "channel": i, "az": float(np.degrees(ring_az[i])), "el": 0.0,
                     "label": f"ring{i}"} for i in range(RING_N)],
             f"Scene {N}次: 仮想スピーカー {RING_N} 本にデコードしてから HRTF で置く")

    # デコーダの素性を表示 (正面 / 22.5° の平面波に対するスピーカーゲイン)
    for N in (1, 3):
        sect, w, D = ring_decoder(N, ring_az)
        for a in (0.0, 22.5):
            b = real_sh(N, np.deg2rad(a), 0.0, norm="sn3d")[0, sect] * w
            gg = D @ b
            print(f"  order {N} src {a:5.1f}°: ring gains {np.round(gg, 2)}  energy {np.sum(gg**2):.2f}")


# ---------------------------------------------------------------- 2 音源 (2 時と 4 時に固定)
KANA = ["あ", "い", "う", "え", "お", "か", "き", "く", "け", "こ", "さ", "し"]
TWO = [  # (タグ, 語彙, 声, 方位)
    ("A", WORDS, "Kyoko", -60.0),                 # 2 時: 女声が数字
    ("B", KANA, "Eddy (日本語（日本）)", -120.0),   # 4 時: 男声がかな
]


def main_two():
    """同じ形式比較を、2 時と 4 時の固定音源 2 本同時で行う。FOA が 2 本を分けられるかを聴く。"""
    print("two sources")
    srcs = []
    for tag, words, voice, az_deg in TWO:
        src, t = make_source(words, voice, tag)
        write(f"two_src{tag}.wav", src)
        srcs.append((src, np.deg2rad(az_deg), az_deg, tag))
    n = len(srcs[0][0])
    spec("two_object", [{"file": f"two_src{tag}.wav", "channel": 0, "az": az_deg, "el": 0.0, "label": tag}
                        for _, _, az_deg, tag in srcs],
         "Object: モノ 2 本 + それぞれの位置")

    names = ["L", "R", "C", "Ls", "Rs"]
    chmap = {"L": 0, "R": 1, "C": 2, "Ls": 4, "Rs": 5}
    ch = np.zeros((n, 6))
    for src, az, _, _ in srcs:
        g = vbap2d_gains(np.full(n, az), [ITU51[k] for k in names])
        for i, k in enumerate(names):
            ch[:, chmap[k]] += src * g[:, i]
    write("two_ch51.wav", ch)
    spec("two_ch51", [{"file": "two_ch51.wav", "channel": chmap[k], "az": ITU51[k], "el": 0.0, "label": k} for k in names],
         "Channel 5.1: 2 本とも R と Rs の間のファントム")

    ring_az = np.deg2rad(np.arange(RING_N) * 360.0 / RING_N)
    for N, name in [(1, "foa"), (3, "hoa3")]:
        ambi = sum(ambix_encode(src, np.full(n, az), np.zeros(n), N) for src, az, _, _ in srcs)
        write(f"two_{name}.wav", ambi)
        ring = ring_decode(ambi, N, ring_az)
        write(f"two_{name}_ring8.wav", ring)
        spec(f"two_{name}", [{"file": f"two_{name}_ring8.wav", "channel": i, "az": float(np.degrees(ring_az[i])),
                              "el": 0.0, "label": f"ring{i}"} for i in range(RING_N)],
             f"Scene {N}次: 2 本の和を仮想スピーカー {RING_N} 本にデコード")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "two":
        main_two()
    else:
        main()
