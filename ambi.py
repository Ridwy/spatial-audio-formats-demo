"""AmbiX (ACN / SN3D) の実球面調和関数。encode.py から使う最小限の部品。"""
from math import factorial

import numpy as np
from scipy.special import lpmv


def acn_nm(N):
    """ACN 順の (n, m) 一覧。"""
    return [(n, m) for n in range(N + 1) for m in range(-n, n + 1)]


def real_sh(N, azi, ele, norm="sn3d"):
    """ambiX 実球面調和関数。戻り値 shape = (len(dirs), (N+1)^2)、列は ACN 順。azi: 左 +、ele: 上 + (rad)。"""
    azi, ele = np.atleast_1d(azi).astype(float), np.atleast_1d(ele).astype(float)
    Y = np.empty((azi.size, (N + 1) ** 2))
    for acn, (n, m) in enumerate(acn_nm(N)):
        am = abs(m)
        k = np.sqrt((2 - (m == 0)) * factorial(n - am) / factorial(n + am))
        if norm == "n3d":
            k *= np.sqrt(2 * n + 1)
        P = (-1) ** am * lpmv(am, n, np.sin(ele))  # scipy の lpmv は Condon-Shortley 位相込み → 打ち消す
        Y[:, acn] = k * P * (np.cos(am * azi) if m >= 0 else np.sin(am * azi))
    return Y
