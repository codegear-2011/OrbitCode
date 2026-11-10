"""Orbit Code: a circular, colour, graph-based 2D code (encoder + decoder).

Pipeline  encode: data -> zlib -> header+CRC -> whiten -> LDPC -> interleave
                  -> 3 bits/node colour (8 colours, Gray) + 1 bit/edge (ring link)
          decode: find 4 anchors -> homography -> Lab soft colour LLRs
                  + Dijkstra edge reading -> sum LLRs over frames
                  -> deinterleave -> LDPC min-sum belief propagation -> CRC
"""
import heapq, math, struct, zlib
from functools import lru_cache
import cv2, numpy as np
from PIL import Image, ImageDraw

S, C = 1000, 500.0                      # canonical canvas
PITCH, NODE_R, R0, R1 = 20, 6.5, 80, 380
ANCH_R, ANCH_S, ANCH_B = 425, 24, 34    # anchor orbit radius, small / big radius
BG, LINE, GOLD = (10, 14, 28), (150, 170, 220), (255, 196, 64)
PALETTE = [(235, 50, 70), (255, 140, 30), (245, 225, 50), (60, 225, 100),
           (40, 225, 235), (60, 100, 255), (235, 60, 225), (245, 245, 245)]
GRAY = [s ^ (s >> 1) for s in range(8)]
SYM_OF = {g: s for s, g in enumerate(GRAY)}
BITS = np.array([[(GRAY[s] >> b) & 1 for b in (2, 1, 0)] for s in range(8)])
# big anchor = top-left, then clockwise
ANCHORS = [(C + ANCH_R * math.cos(math.radians(a)), C + ANCH_R * math.sin(math.radians(a)))
           for a in (225, 315, 45, 135)]
CAL = [(C + 36 * math.cos(k * math.pi / 4), C + 36 * math.sin(k * math.pi / 4)) for k in range(8)]


# ---------------------------------------------------------------- layout (graph)
@lru_cache(None)
def layout():
    """Nodes on concentric rings; edges link neighbours on the same ring."""
    nodes, edges = [], []
    for j, r in enumerate(range(R0, R1 + 1, PITCH)):
        n = int(2 * math.pi * r / PITCH)
        idx = {}
        for i in range(n):
            a = 2 * math.pi * (i + 0.5 * (j % 2)) / n + j * 0.37
            p = (C + r * math.cos(a), C + r * math.sin(a))
            if min(math.dist(p, q) for q in ANCHORS) < 62:
                continue
            idx[i] = len(nodes)
            nodes.append(p)
        edges += [(idx[i], idx[(i + 1) % n]) for i in idx if (i + 1) % n in idx]
    return nodes, edges


# ---------------------------------------------------------------- LDPC
class LDPC:
    def __init__(self, n, m, seed=7):
        rng = np.random.default_rng(seed)
        deg, H = np.zeros(m), np.zeros((m, n), np.uint8)
        for c in range(n):                       # column weight 3, balanced rows
            rows = np.argpartition(deg + rng.random(m) * 0.9, 3)[:3]
            H[rows, c] = 1
            deg[rows] += 1
        self.n, self.m = n, m
        rows = [np.flatnonzero(H[i]) for i in range(m)]
        self.chk = np.full((m, max(map(len, rows))), n)
        for i, r in enumerate(rows):
            self.chk[i, :len(r)] = r
        self.mask = self.chk < n
        P, piv, rk = np.packbits(H, axis=1), [], 0   # GF(2) reduction -> systematic encoder
        for c in range(n):
            if rk == m:
                break
            bit = lambda col=c: (P[:, col >> 3] >> (7 - (col & 7))) & 1
            nz = np.flatnonzero(bit()[rk:])
            if not len(nz):
                continue
            p = rk + nz[0]
            P[[rk, p]] = P[[p, rk]]
            hit = np.flatnonzero(bit())
            P[hit[hit != rk]] ^= P[rk]
            piv.append(c)
            rk += 1
        self.piv, self.k = np.array(piv), n - rk
        self.info = np.setdiff1d(np.arange(n), self.piv)
        self.R = np.unpackbits(P[:rk], axis=1)[:, :n][:, self.info].astype(np.int32)

    def encode(self, u):
        x = np.zeros(self.n, np.uint8)
        x[self.info] = u
        x[self.piv] = (self.R @ u.astype(np.int32)) & 1
        return x

    def decode(self, llr, iters=60, alpha=0.8):
        """Normalised min-sum. llr > 0 means bit 0. Returns (bits, converged)."""
        L = np.append(np.clip(llr, -20, 20), 0.0)
        msg = np.zeros(self.chk.shape)
        ar, cols = np.arange(self.m), np.arange(self.chk.shape[1])[None, :]
        for it in range(iters + 1):
            tot = L + np.bincount(self.chk[self.mask], msg[self.mask], self.n + 1)
            hard = (tot < 0).astype(np.uint8)
            hard[self.n] = 0
            ok = not (hard[self.chk].sum(1) & 1).any()
            if ok or it == iters:
                break
            v = np.where(self.mask, tot[self.chk] - msg, 0.0)
            sg = np.where(v < 0, -1.0, 1.0)
            a = np.where(self.mask, np.abs(v), np.inf)
            i1 = a.argmin(1)
            m1 = a[ar, i1].copy()
            a[ar, i1] = np.inf
            m2 = a.min(1)
            mag = np.where(cols == i1[:, None], m2[:, None], m1[:, None])
            msg = np.where(self.mask, alpha * sg.prod(1)[:, None] * sg * mag, 0.0)
        return hard[:self.n], ok


@lru_cache(None)
def codec():
    nodes, edges = layout()
    n = 3 * len(nodes) + len(edges)
    return LDPC(n, n // 2)


@lru_cache(None)
def perm(n):
    return np.random.default_rng(5).permutation(n)       # interleaver


def capacity():
    return codec().k // 8 - 7        # bytes, worst case (incompressible data)


# ---------------------------------------------------------------- message
def whiten(k):
    return np.random.default_rng(99).integers(0, 2, k, dtype=np.uint8)


def pack(data, k):
    z = zlib.compress(data, 9)
    flag, body = (1, z) if len(z) < len(data) else (0, data)
    msg = struct.pack(">BHI", flag, len(body), zlib.crc32(body)) + body
    if len(msg) * 8 > k:
        raise ValueError(f"Data too large: max about {capacity()} bytes (less if not compressible).")
    bits = np.unpackbits(np.frombuffer(msg, np.uint8))
    return np.concatenate([bits, np.zeros(k - len(bits), np.uint8)]) ^ whiten(k)


def unpack(bits):
    b = np.packbits(bits ^ whiten(len(bits))).tobytes()
    flag, ln, crc = struct.unpack(">BHI", b[:7])
    body = b[7:7 + ln]
    if len(body) != ln or zlib.crc32(body) != crc:
        raise ValueError("CRC mismatch: the code could not be read reliably.")
    return zlib.decompress(body) if flag else body


# ---------------------------------------------------------------- encoder
def encode(data, scale=2.0):
    nodes, edges = layout()
    cd = codec()
    tx = cd.encode(pack(data, cd.k))[perm(cd.n)]
    N = len(nodes)
    syms = tx[:3 * N].reshape(N, 3) @ np.array([4, 2, 1])
    return render([PALETTE[SYM_OF[int(v)]] for v in syms], tx[3 * N:], scale)


def render(colors, ebits, scale):
    nodes, edges = layout()
    f = 2 * scale                                        # 2x supersampling
    img = Image.new("RGB", (int(S * f),) * 2, BG)
    d = ImageDraw.Draw(img)

    def disc(p, r, c):
        d.ellipse([(p[0] - r) * f, (p[1] - r) * f, (p[0] + r) * f, (p[1] + r) * f], fill=c)

    for r in range(R0, R1 + 1, PITCH):                   # faint orbit guides (not read)
        d.ellipse([(C - r) * f, (C - r) * f, (C + r) * f, (C + r) * f], outline=(26, 32, 54), width=int(f))
    d.arc([(C - 485) * f, (C - 485) * f, (C + 485) * f, (C + 485) * f], 15, 345, fill=LINE, width=int(5 * f))
    for (a, b), bit in zip(edges, ebits):
        if bit:
            d.line([(nodes[a][0] * f, nodes[a][1] * f), (nodes[b][0] * f, nodes[b][1] * f)],
                   fill=LINE, width=int(3 * f))
    for p, c in zip(nodes, colors):
        disc(p, NODE_R, c)
    for p, c in zip(CAL, PALETTE):                       # calibration colours
        disc(p, 7.5, c)
    for i, p in enumerate(ANCHORS):
        r = ANCH_B if i == 0 else ANCH_S
        disc(p, r, GOLD); disc(p, r * 0.62, BG); disc(p, r * 0.28, GOLD)
    return img.resize((int(S * scale),) * 2, Image.LANCZOS)


# ---------------------------------------------------------------- detector
def find_anchors(img):
    mx = img.max(2)
    _, bw = cv2.threshold(mx, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cs, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cand = []
    for c in cs:
        A, P = cv2.contourArea(c), cv2.arcLength(c, True)
        if A < 30 or P == 0 or 4 * math.pi * A / P ** 2 < 0.7:
            continue
        M = cv2.moments(c)
        cand.append((A, M["m10"] / M["m00"], M["m01"] / M["m00"]))
    a = sorted(cand, reverse=True)[:4]
    if len(a) < 4 or not 1.3 < a[0][0] / np.mean([x[0] for x in a[1:]]) < 3.2:
        raise ValueError("Anchors not found. Make sure the whole code is visible.")
    cx, cy = np.mean([x[1] for x in a]), np.mean([x[2] for x in a])
    ang = lambda x: math.atan2(x[2] - cy, x[1] - cx)
    rest = sorted(a[1:], key=lambda x: (ang(x) - ang(a[0])) % (2 * math.pi))
    return np.float32([(x[1], x[2]) for x in [a[0]] + rest])


def rectify(img):
    H = cv2.getPerspectiveTransform(find_anchors(img), np.float32(ANCHORS))
    return cv2.warpPerspective(img, H, (S, S), flags=cv2.INTER_CUBIC)


def edge_strength(fg, p, q):
    """Dijkstra least-cost path between two nodes; mean foreground along it."""
    x0, x1 = int(min(p[0], q[0])) - 4, int(max(p[0], q[0])) + 5
    y0, y1 = int(min(p[1], q[1])) - 4, int(max(p[1], q[1])) + 5
    w = fg[y0:y1, x0:x1].tolist()
    h, wd = len(w), len(w[0])
    s, t = (round(p[1]) - y0, round(p[0]) - x0), (round(q[1]) - y0, round(q[0]) - x0)
    dist, prev, pq = {s: 0.0}, {}, [(0.0, s)]
    while pq:
        dc, u = heapq.heappop(pq)
        if u == t:
            break
        if dc > dist[u]:
            continue
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                v = (u[0] + dy, u[1] + dx)
                if (dy or dx) and 0 <= v[0] < h and 0 <= v[1] < wd:
                    nd = dc + (1 + 12 * (1 - w[v[0]][v[1]])) * (1.414 if dy and dx else 1)
                    if nd < dist.get(v, 1e18):
                        dist[v], prev[v] = nd, u
                        heapq.heappush(pq, (nd, v))
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    far = [v for v in path if min(math.dist(v, s), math.dist(v, t)) > NODE_R + 2.5] or path
    return float(np.mean([w[v[0]][v[1]] for v in far]))


def read_llr(flat):
    """Soft information (LLR, >0 = bit 0) for every transmitted bit."""
    nodes, edges = layout()
    lab = cv2.cvtColor(flat, cv2.COLOR_BGR2LAB).astype(np.float32)

    def samp(p):
        x, y = int(round(p[0])), int(round(p[1]))
        return np.median(lab[y - 1:y + 2, x - 1:x + 2].reshape(-1, 3), 0)

    ref = np.array([samp(p) for p in CAL])               # lighting-adapted palette
    X = np.array([samp(p) for p in nodes])
    d2 = ((X[:, None] - ref[None]) ** 2).sum(2)
    rd = np.sqrt(((ref[:, None] - ref[None]) ** 2).sum(2))
    np.fill_diagonal(rd, 1e9)
    sig2 = (0.35 * np.median(rd.min(1))) ** 2
    p = np.exp(-(d2 - d2.min(1, keepdims=True)) / (2 * sig2))
    p /= p.sum(1, keepdims=True)
    llr_n = np.log((p @ (1 - BITS) + 1e-6) / (p @ BITS + 1e-6)).reshape(-1)
    fg = np.clip((flat.max(2).astype(np.float32) - 70) / 110, 0, 1)
    llr_e = [(0.45 - edge_strength(fg, nodes[a], nodes[b])) * 14 for a, b in edges]
    return np.concatenate([llr_n, llr_e])


def decode_images(imgs):
    """Decode one or several frames of the same code (LLRs are summed)."""
    cd, total, used, err = codec(), 0, 0, None
    for im in imgs:
        try:
            total = total + read_llr(rectify(im))
            used += 1
        except ValueError as e:
            err = e
    if not used:
        raise err or ValueError("No image given.")
    cw = np.empty(cd.n)
    cw[perm(cd.n)] = total
    bits, ok = cd.decode(cw)
    if not ok:
        raise ValueError("Error correction failed: the image is too damaged or blurry.")
    return unpack(bits[cd.info]), used
