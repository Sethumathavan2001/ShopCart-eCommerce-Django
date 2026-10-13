"""Image helpers: normalise product photos and build category cover images."""
import io

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

PRODUCT_SIZE = 600
COVER_SIZE = (800, 600)


def _flatten(img):
    """Return an RGB image with any transparency composited onto white."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
        bg = Image.new('RGB', img.size, 'white')
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert('RGB')


def trim_whitespace(img, tolerance=18):
    """Crop away near-white borders around the product."""
    bg = Image.new('RGB', img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg).convert('L').point(lambda v: 255 if v > tolerance else 0)
    box = diff.getbbox()
    return img.crop(box) if box else img


def square_product_image(source, size=PRODUCT_SIZE, margin=0.08):
    """
    Trim, centre and pad a product photo onto a white square.
    `source` is a path or file object. Returns JPEG bytes.
    """
    img = trim_whitespace(_flatten(Image.open(source)))
    inner = int(size * (1 - 2 * margin))
    scale = inner / max(img.size)
    if scale < 1:
        img.thumbnail((inner, inner), Image.LANCZOS)
    elif scale > 1:
        # Source photos are small thumbnails; upscale gently and sharpen
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    canvas = Image.new('RGB', (size, size), 'white')
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    buf = io.BytesIO()
    canvas.save(buf, 'JPEG', quality=88, optimize=True, progressive=True)
    return buf.getvalue()


def _hex(color):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def tint_of(accent, amount=0.08):
    """Same result as CSS color-mix(in srgb, accent 8%, white), so images blend into tinted panels."""
    return '#' + ''.join(f'{round(c * amount + 255 * (1 - amount)):02x}' for c in _hex(accent))


def category_cover(image_paths, tint=None, accent='#4f46e5'):
    """Compose up to three product photos as floating cards on a tinted background. Returns JPEG bytes."""
    tint = tint or tint_of(accent)
    w, h = COVER_SIZE
    scale = 2  # draw at 2x and downsample for smooth edges
    W, H = w * scale, h * scale
    base = Image.new('RGB', (W, H), _hex(tint))
    draw = ImageDraw.Draw(base)

    # Soft decorative circles
    acc = _hex(accent)
    soft = tuple(int(c + (255 - c) * 0.82) for c in acc)
    draw.ellipse((W * 0.62, -H * 0.25, W * 1.25, H * 0.55), fill=soft)
    draw.ellipse((-W * 0.2, H * 0.6, W * 0.3, H * 1.3), fill=soft)

    layouts = {
        1: [(0.5, 0.5, 0.62)],
        2: [(0.33, 0.52, 0.46), (0.68, 0.48, 0.46)],
        3: [(0.24, 0.56, 0.36), (0.76, 0.56, 0.36), (0.5, 0.44, 0.44)],
    }
    paths = list(image_paths)[:3]
    for cx, cy, frac in layouts.get(len(paths), []):
        path = paths.pop(0)
        side = int(H * frac)
        try:
            card = Image.open(io.BytesIO(square_product_image(path, size=side, margin=0.1)))
        except Exception:
            continue
        x, y = int(W * cx - side / 2), int(H * cy - side / 2)
        radius = int(side * 0.08)

        shadow = Image.new('L', (W, H), 0)
        ImageDraw.Draw(shadow).rounded_rectangle((x + 10, y + 26, x + side + 10, y + side + 26), radius, fill=90)
        shadow = shadow.filter(ImageFilter.GaussianBlur(28))
        base = Image.composite(Image.new('RGB', (W, H), tuple(int(c * 0.75) for c in _hex(tint))), base, shadow)

        mask = Image.new('L', (side, side), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, side - 1, side - 1), radius, fill=255)
        base.paste(card, (x, y), mask)

    out = base.resize((w, h), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, 'JPEG', quality=88, optimize=True, progressive=True)
    return buf.getvalue()
