"""Straighten perspective, crop to the design, and retouch the installation photos.

Usage: python3 fixphotos.py <images_dir> <out_dir>
"""
import sys
import cv2
import numpy as np

SRC, OUT = sys.argv[1:3]

# Per photo: the partition facade corners (TL, TR, BR, BL) in the original image,
# how strongly to straighten (1 = fully frontal), target aspect (w/h) of the facade,
# and crop margins around the facade as fractions of its size (left, top, right, bottom).
CFG = {
    1: dict(quad=[(225, 372), (1262, 202), (1197, 1150), (306, 893)], strength=0.85, aspect=1.18,
            margin=(0.04, 0.06, 0.08, 0.07)),
    2: dict(quad=[(45, 235), (1795, 385), (1628, 1145), (262, 1320)], strength=0.9, aspect=1.85,
            margin=(0.02, 0.07, 0.02, 0.07)),
    3: dict(quad=[(405, 350), (893, 342), (805, 1495), (440, 1440)], strength=0.8, aspect=0.43,
            margin=(0.75, 0.07, 0.75, 0.05)),
    4: dict(quad=[(455, 365), (1335, 95), (1300, 1235), (468, 865)], strength=0.6, aspect=1.2,
            margin=(0.05, 0.06, 0.02, 0.05)),
}


def straighten(img, quad, strength, aspect, margin):
    q = np.float32(quad)
    top = np.linalg.norm(q[1] - q[0]); bot = np.linalg.norm(q[2] - q[3])
    left = np.linalg.norm(q[3] - q[0]); right = np.linalg.norm(q[2] - q[1])
    h = max(left, right); w = h * aspect
    c = q.mean(0)
    rect = np.float32([(c[0] - w / 2, c[1] - h / 2), (c[0] + w / 2, c[1] - h / 2),
                       (c[0] + w / 2, c[1] + h / 2), (c[0] - w / 2, c[1] + h / 2)])
    dst = q * (1 - strength) + rect * strength
    M = cv2.getPerspectiveTransform(q, dst)
    # crop window around the (corrected) facade
    x0, y0 = dst[:, 0].min(), dst[:, 1].min(); x1, y1 = dst[:, 0].max(), dst[:, 1].max()
    fw, fh = x1 - x0, y1 - y0
    x0 -= margin[0] * fw; x1 += margin[2] * fw; y0 -= margin[1] * fh; y1 += margin[3] * fh
    T = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], np.float64)
    size = (int(x1 - x0), int(y1 - y0))
    out = cv2.warpPerspective(img, T @ M, size, flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
    valid = cv2.warpPerspective(np.full(img.shape[:2], 255, np.uint8), T @ M, size, flags=cv2.INTER_NEAREST)
    return out, valid


def trim_invalid(img, valid):
    """Shrink the crop until no pixel from outside the original photo remains."""
    ys, xs = np.where(valid > 0)
    x0, x1, y0, y1 = 0, img.shape[1], 0, img.shape[0]
    for _ in range(400):
        win = valid[y0:y1, x0:x1]
        if win.min() > 0:
            break
        bad = win == 0
        # cut the side with the most invalid pixels
        sides = {"t": bad[0].sum(), "b": bad[-1].sum(), "l": bad[:, 0].sum(), "r": bad[:, -1].sum()}
        s = max(sides, key=sides.get)
        if s == "t": y0 += 4
        elif s == "b": y1 -= 4
        elif s == "l": x0 += 4
        else: x1 -= 4
    return img[y0:y1, x0:x1]


def retouch(img):
    # neutral white balance (gray-world, damped so the designs keep their colours)
    f = img.astype(np.float32)
    means = f.reshape(-1, 3).mean(0)
    gain = (means.mean() / means) ** 0.6
    f *= gain
    img = np.clip(f, 0, 255).astype(np.uint8)
    # local contrast on lightness only
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(l)
    img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    # gentle brightness lift + saturation
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] *= 1.12
    hsv[..., 2] = 255 * (hsv[..., 2] / 255) ** 0.92
    img = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    # denoise compression artefacts, then sharpen
    img = cv2.fastNlMeansDenoisingColored(img, None, 3, 3, 7, 21)
    blur = cv2.GaussianBlur(img, (0, 0), 1.4)
    img = cv2.addWeighted(img, 1.6, blur, -0.6, 0)
    # soft top/bottom vignette so floor and ceiling recede and the design pops
    h, w = img.shape[:2]
    y = np.linspace(-1, 1, h)[:, None]; x = np.linspace(-1, 1, w)[None, :]
    v = 1 - 0.28 * np.clip(np.abs(y) - 0.55, 0, 1) / 0.45 - 0.12 * np.clip(np.abs(x) - 0.7, 0, 1) / 0.3
    return np.clip(img.astype(np.float32) * v[..., None], 0, 255).astype(np.uint8)


for i, cfg in CFG.items():
    img = cv2.imread(f"{SRC}/{i}.jpg")
    out, valid = straighten(img, **cfg)
    out = trim_invalid(out, valid)
    out = retouch(out)
    cv2.imwrite(f"{OUT}/{i}.jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(i, out.shape)
