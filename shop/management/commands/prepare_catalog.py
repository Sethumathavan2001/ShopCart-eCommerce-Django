"""
Clean the imported catalogue and make it production-ready.

    python manage.py prepare_catalog            # clean data + build images
    python manage.py prepare_catalog --dry-run  # show what would change

Safe to run repeatedly: products are only cleaned once (detected by the raw
Amazon ASIN still sitting in the brand field), images only once (detected by
their location under products/).
"""
import math
import random
import re
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from shop.imaging import category_cover, square_product_image
from shop.models import Catagory, OrderItem, Products, UserProfile, WalletTransaction

ASIN_RE = re.compile(r'^B0[A-Z0-9]{8}$')
SPLIT_RE = re.compile(r'\s*\|\s*|\s+[-–—]\s+|,\s+|:\s+|\s+\(|\)\s*')
TRAILING_JUNK = re.compile(r'[\s,;:|\-–&/(]+$|\s+(with|for|and|of|in|to|the|by|&)$', re.I)
GENERIC_FIRST_WORDS = {'new', 'the', 'premium', 'original', 'combo', 'pack', 'set', 'best', 'fast-acting'}
# Brands whose name is more than one word
MULTI_WORD_BRANDS = ['Amazon Basics', 'Eat Anytime', 'Old Tree', "Knick Knack's", 'Deve Herbes', 'AG Taste',
                     'RN Toys', 'J Organics', 'A TO Z HUB', 'Happy Bar', 'Mojo Toys', 'Home-Complete',
                     'Skip Hop', 'Fisher-Price', 'Bright Starts', 'Baby Moo', 'Mee Mee', 'R for Rabbit',
                     'The Whole Truth', 'Plum', 'Mamaearth', 'Himalaya', "Johnson's"]
TITLE_MAX = 70

CATEGORY_STYLE = {
    'Grocery & Gourmet Foods': ('bi-basket2', '#ecfdf5', '#16a34a',
                                'Pantry staples, healthy snacks, sweets and gourmet treats — delivered fresh.'),
    'Beauty': ('bi-stars', '#fdf2f8', '#db2777',
               'Skincare, haircare, fragrances and wellness essentials from brands you trust.'),
    'Electronics': ('bi-cpu', '#eff6ff', '#2563eb',
                    'Cables, chargers, audio and smart accessories for every device you own.'),
    'Health & Personal Care': ('bi-heart-pulse', '#f0fdfa', '#0d9488',
                               'Everyday health, hygiene and personal care products for the whole family.'),
    'Baby Products': ('bi-balloon-heart', '#fff7ed', '#f97316',
                      'Toys, swings, rockers and care essentials for your little ones.'),
}
DEFAULT_STYLE = ('bi-grid', '#eef2ff', '#4f46e5', '')
CATEGORY_TAGLINES = {
    'Grocery & Gourmet Foods': 'Everyday essentials, delivered fresh',
    'Beauty': 'Glow up with beauty favourites',
    'Electronics': 'Upgrade your tech setup',
    'Health & Personal Care': 'Care for the ones you love',
    'Baby Products': 'Little joys for little ones',
}


def clean_text(s):
    s = s.replace('‎', '').replace('\xa0', ' ')
    s = re.sub(r'(?<=[A-Za-z)]),(?=\S)', ', ', s)  # "Cable,6 Feet" -> "Cable, 6 Feet" (keeps 1,000)
    s = re.sub(r'\s+', ' ', s).strip()
    return re.sub(r'\s+([,.;:!?])', r'\1', s)


def strip_junk(s):
    prev = None
    while prev != s:
        prev, s = s, TRAILING_JUNK.sub('', s).strip()
    return s


def segments(raw):
    return [strip_junk(p) for p in SPLIT_RE.split(raw) if p and strip_junk(p)]


def clean_title(raw):
    """Turn a long marketplace title into a short, readable product name."""
    raw = clean_text(raw)
    parts = segments(raw)
    if not parts:
        return raw[:TITLE_MAX]
    title = parts[0]
    # A very short first part ("Fitspire Quinoa Almond") reads better with the next part
    if len(title) < 30 and len(parts) > 1 and len(title) + len(parts[1]) + 3 <= 60:
        title = f'{title} - {parts[1]}'
    if len(title) > TITLE_MAX:
        cut = title[:TITLE_MAX + 1]
        title = cut[:cut.rfind(' ')] if ' ' in cut else cut[:TITLE_MAX]
    return strip_junk(title)


def brand_from(raw):
    text = clean_text(raw)
    for brand in MULTI_WORD_BRANDS:
        if text.lower().startswith(brand.lower() + ' '):
            return brand
    words = [w.strip(',.|:()') for w in text.split()]
    words = [w for w in words if w]
    while words and words[0].lower() in GENERIC_FIRST_WORDS:
        words.pop(0)
    if not words:
        return 'ShopCart'
    brand = words[0]
    # Very short tokens ("AG", "RN") are usually the first half of a two-word brand
    if len(brand) <= 2 and len(words) > 1:
        brand = f'{brand} {words[1]}'
    if brand.islower():
        brand = brand.title()
    return brand[:60]


def unique_title(raw, taken):
    """clean_title(), extended with extra detail from the raw title when the short form is already taken."""
    title = clean_title(raw)
    if title.lower() not in taken:
        return title
    for extra in segments(clean_text(raw))[1:]:
        candidate = f'{title} - {extra}'
        if extra.lower() not in title.lower() and len(candidate) <= 110 and candidate.lower() not in taken:
            return candidate
    n = 2
    while f'{title} (Variant {n})'.lower() in taken:
        n += 1
    return f'{title} (Variant {n})'


def build_description(raw, title, category):
    """Use the extra detail packed into the raw title as a highlights list."""
    raw = clean_text(raw)
    parts = segments(raw)
    if len(raw) >= 145 and parts:
        parts = parts[:-1]  # the original import truncated titles mid-word
    title_l = title.lower()
    highlights, seen = [], set()
    for p in parts:
        key = p.lower()
        if len(p) < 4 or key in seen or key in title_l:
            continue
        seen.add(key)
        highlights.append(p[0].upper() + p[1:])

    intro = f'{title}. A quality pick from our {category} range, carefully packed and shipped fast.'
    if not highlights:
        return intro
    text = intro + '\n\nHighlights:\n' + '\n'.join(f'• {h}' for h in highlights[:6])
    return text[:495]


def nice_mrp(selling, discount):
    """Original price for a discount, rounded up to a price ending in 9."""
    mrp = selling / (1 - discount / 100)
    return float(math.ceil((mrp + 1) / 10) * 10 - 1) if mrp >= 100 else float(math.ceil(mrp))


class Command(BaseCommand):
    help = 'Clean product data, generate product/category images and reconcile wallets.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show changes without saving')
        parser.add_argument('--skip-images', action='store_true', help='Do not (re)build images')

    def handle(self, *args, dry_run=False, skip_images=False, **opts):
        self.dry_run = dry_run
        self.verbosity = opts.get("verbosity", 1)
        with transaction.atomic():
            self.remove_duplicates()
            if self.clean_products():
                self.pick_trending()  # only re-pick when raw products were just cleaned
            self.polish_short_titles()
            self.style_categories()
            self.reconcile_wallets()
            if dry_run:
                transaction.set_rollback(True)
        if not skip_images and not dry_run:
            self.build_product_images()
            self.build_category_covers()
        self.stdout.write(self.style.SUCCESS('Catalogue ready.' + (' (dry run, nothing saved)' if dry_run else '')))

    # ------------------------------------------------------------------ data
    def remove_duplicates(self):
        """Delete exact duplicates among raw (not yet cleaned) products: same title in the same category."""
        seen, removed = set(), 0
        ordered = set(OrderItem.objects.values_list('product_id', flat=True))
        for p in Products.objects.filter(vendor__regex=ASIN_RE.pattern).order_by('id'):
            key = (clean_text(p.name).lower(), p.category_id)
            if key in seen and p.id not in ordered:
                p.delete()
                removed += 1
            else:
                seen.add(key)
        self.stdout.write(f'Removed {removed} duplicate products')

    def clean_products(self):
        now = timezone.now()
        cleaned = 0
        used = defaultdict(set)  # category -> lower-cased names already taken
        for name, cat in Products.objects.exclude(vendor__regex=ASIN_RE.pattern).values_list('name', 'category_id'):
            used[cat].add(name.lower())
        for p in Products.objects.select_related('category').filter(vendor__regex=r'^B0[A-Z0-9]{8}$'):
            rng = random.Random(p.id)  # deterministic per product
            raw = p.name
            p.sku = p.vendor
            p.vendor = brand_from(raw)
            p.name = unique_title(raw, used[p.category_id])
            if p.name.lower().startswith(p.vendor.lower()):
                p.name = p.vendor + p.name[len(p.vendor):]  # consistent brand casing
            used[p.category_id].add(p.name.lower())
            if clean_text(p.description).lower().startswith(clean_text(raw).lower()[:60]):
                p.description = build_description(raw, p.name, p.category.name)

            discount = rng.choices([0, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60],
                                   weights=[6, 8, 12, 14, 14, 12, 10, 8, 7, 5, 4])[0]
            p.orginal_price = nice_mrp(p.selling_price, discount) if discount else p.selling_price

            roll = rng.random()
            p.quantity = 0 if roll < 0.04 else rng.randint(1, 6) if roll < 0.14 else rng.randint(12, 180)
            p.save()
            Products.objects.filter(id=p.id).update(created_at=now - timedelta(days=rng.randint(0, 150),
                                                                               minutes=rng.randint(0, 1440)))
            cleaned += 1
            if self.verbosity > 1:
                self.stdout.write(f'  {raw[:60]!r} -> {p.name!r} [{p.vendor}]')
        self.stdout.write(f'Cleaned {cleaned} products')
        return cleaned

    def pick_trending(self):
        Products.objects.update(trending=False)
        picked = 0
        for cat in Catagory.objects.all():
            items = list(Products.objects.filter(category=cat, status=False, quantity__gt=5).order_by('id'))
            rng = random.Random(cat.id)
            for p in rng.sample(items, min(4, len(items))):
                p.trending = True
                p.save(update_fields=['trending'])
                picked += 1
        self.stdout.write(f'Marked {picked} trending products')

    def polish_short_titles(self, min_len=22):
        """Titles like "Amazon Brand" say nothing; extend them with the first highlight."""
        fixed = 0
        for p in Products.objects.all():
            if len(p.name) >= min_len:
                continue
            first = next((line[1:].strip() for line in p.description.splitlines() if line.startswith('•')), '')
            if not first:
                continue
            title = f'{p.name} - {first}'
            if len(title) > TITLE_MAX:
                cut = title[:TITLE_MAX + 1]
                title = cut[:cut.rfind(' ')]
            title = strip_junk(title)
            if len(title) <= len(p.name):
                continue
            if p.description.startswith(p.name + '.'):
                p.description = title + p.description[len(p.name):]
            p.name = title
            p.save(update_fields=['name', 'description'])
            fixed += 1
        self.stdout.write(f'Expanded {fixed} short titles')

    def style_categories(self):
        for cat in Catagory.objects.all():
            icon, _, accent, description = CATEGORY_STYLE.get(cat.name, DEFAULT_STYLE)
            cat.icon = icon
            cat.color = accent
            if not cat.tagline:
                cat.tagline = CATEGORY_TAGLINES.get(cat.name, f'Discover {cat.name}')
            if description and (not cat.description or cat.description.lower().startswith(('this', 'all '))):
                cat.description = description
            cat.save(update_fields=['icon', 'color', 'tagline', 'description'])
        self.stdout.write('Styled categories')

    def reconcile_wallets(self):
        """Make every wallet balance match its transaction ledger and never be negative."""
        for profile in UserProfile.objects.select_related('user'):
            ledger = WalletTransaction.objects.filter(user=profile.user)
            credit = ledger.filter(type='credit').aggregate(s=Sum('amount'))['s'] or Decimal('0')
            debit = ledger.filter(type='debit').aggregate(s=Sum('amount'))['s'] or Decimal('0')
            ledger_balance = credit - debit
            target = max(profile.ewallet_amount, Decimal('0'))
            if ledger_balance != target:
                diff = target - ledger_balance
                WalletTransaction.objects.create(
                    user=profile.user, type='credit' if diff > 0 else 'debit', amount=abs(diff), balance=target,
                    comment='Opening balance' if not ledger.exists() else 'Balance correction')
                self.stdout.write(f'  wallet {profile.user.username}: ledger {ledger_balance} -> {target}')
            if profile.ewallet_amount != target:
                profile.ewallet_amount = target
                profile.save(update_fields=['ewallet_amount'])

    # ------------------------------------------------------------------ images
    def build_product_images(self):
        done = 0
        for p in Products.objects.exclude(product_image='').exclude(image_ready_q()):
            try:
                with p.product_image.open('rb') as fh:
                    data = square_product_image(fh)
            except (FileNotFoundError, OSError) as exc:
                self.stderr.write(f'  skip {p.id}: {exc}')
                continue
            name = f'products/{p.id}.jpg'
            if default_storage.exists(name):
                default_storage.delete(name)
            # The original upload is kept; only the reference moves to the cleaned copy
            Products.objects.filter(id=p.id).update(product_image=default_storage.save(name, ContentFile(data)))
            done += 1
        self.stdout.write(f'Built {done} product images')

    def build_category_covers(self):
        for cat in Catagory.objects.all():
            accent = cat.color or DEFAULT_STYLE[2]
            picks = (Products.objects.filter(category=cat, status=False).exclude(product_image='')
                     .order_by('-trending', 'id')[:3])
            paths = [settings.MEDIA_ROOT / p.product_image.name for p in picks]
            if not paths:
                continue
            name = f'categories/{cat.id}.jpg'
            if default_storage.exists(name):
                default_storage.delete(name)
            Catagory.objects.filter(id=cat.id).update(
                image=default_storage.save(name, ContentFile(category_cover(paths, accent=accent))))
        self.stdout.write('Built category cover images')


def image_ready_q():
    return Q(product_image__startswith='products/')
