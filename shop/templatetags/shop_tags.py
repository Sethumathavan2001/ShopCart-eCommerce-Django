from decimal import Decimal

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma
from django.utils.html import format_html, mark_safe

register = template.Library()


@register.filter
def inr(value):
    """Format a number as Rs. 1,234 (or Rs. 1,234.50 when it has paise)."""
    try:
        value = Decimal(str(value))
    except Exception:
        return value
    if value == value.to_integral():
        return f"Rs. {intcomma(int(value))}"
    return f"Rs. {intcomma(f'{value:.2f}')}"


@register.simple_tag
def stars(rating):
    """Render 5 Bootstrap-icon stars for a rating (supports halves)."""
    rating = float(rating or 0)
    html = []
    for i in range(1, 6):
        if rating >= i:
            html.append('<i class="bi bi-star-fill"></i>')
        elif rating >= i - 0.5:
            html.append('<i class="bi bi-star-half"></i>')
        else:
            html.append('<i class="bi bi-star"></i>')
    return format_html('<span class="stars">{}</span>', mark_safe(''.join(html)))


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Return the current querystring with some parameters replaced (used for sort/pagination links)."""
    params = context['request'].GET.copy()
    if 'page' not in kwargs:
        params.pop('page', None)  # Changing a filter resets pagination
    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = str(value)
    return params.urlencode()


@register.filter
def initials(user):
    name = (user.get_full_name() or user.username).strip()
    parts = name.split()
    return ''.join(p[0] for p in parts[:2]).upper() or '?'


@register.filter
def split_ranges(value):
    """'0,499,Under 499|500,999,500 – 999' -> [('0', '499', 'Under 499'), ...] for price shortcut chips."""
    return [tuple(part.split(',', 2)) for part in value.split('|')]
