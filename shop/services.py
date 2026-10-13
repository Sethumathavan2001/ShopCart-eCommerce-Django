"""Business logic shared by views: cart totals, coupons and wallet movements."""
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from .models import Cartlist, Coupon, UserProfile, WalletTransaction

FREE_SHIPPING_ABOVE = Decimal(str(getattr(settings, 'FREE_SHIPPING_ABOVE', 499)))
SHIPPING_CHARGE = Decimal(str(getattr(settings, 'SHIPPING_CHARGE', 40)))
MAX_QTY_PER_ITEM = getattr(settings, 'MAX_QTY_PER_ITEM', 10)

COUPON_SESSION_KEY = 'coupon_code'


class WalletError(Exception):
    pass


def get_session_coupon(request):
    code = request.session.get(COUPON_SESSION_KEY)
    if not code:
        return None
    return Coupon.objects.filter(code=code).first()


def cart_summary(request):
    """Return a dict with the user's cart items and all totals."""
    items = list(Cartlist.objects.filter(user=request.user).select_related('product', 'product__category'))
    subtotal = sum((i.line_total for i in items), Decimal('0'))
    mrp_total = sum((i.line_mrp for i in items), Decimal('0'))

    coupon = get_session_coupon(request)
    coupon_discount = Decimal('0')
    coupon_error = None
    if coupon:
        ok, msg = coupon.check_valid(subtotal)
        if ok:
            coupon_discount = coupon.discount_for(subtotal)
        else:
            coupon_error = msg
            coupon = None
            request.session.pop(COUPON_SESSION_KEY, None)

    after_discount = subtotal - coupon_discount
    shipping = Decimal('0') if (not items or subtotal >= FREE_SHIPPING_ABOVE) else SHIPPING_CHARGE
    total = after_discount + shipping

    return {
        'items': items,
        'item_count': sum(i.quantity for i in items),
        'mrp_total': mrp_total,
        'product_savings': mrp_total - subtotal,
        'subtotal': subtotal,
        'coupon': coupon,
        'coupon_discount': coupon_discount,
        'coupon_error': coupon_error,
        'shipping': shipping,
        'free_shipping_above': FREE_SHIPPING_ABOVE,
        'free_shipping_gap': max(FREE_SHIPPING_ABOVE - subtotal, Decimal('0')),
        'total': total,
        'has_stock_issue': any(i.quantity > i.product.quantity or i.product.status for i in items),
    }


def get_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@transaction.atomic
def wallet_credit(user, amount, comment):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError('Amount must be greater than zero.')
    get_profile(user)
    profile = UserProfile.objects.select_for_update().get(user=user)
    profile.ewallet_amount += amount
    profile.save(update_fields=['ewallet_amount'])
    WalletTransaction.objects.create(user=user, type='credit', amount=amount,
                                     balance=profile.ewallet_amount, comment=comment[:100])
    return profile.ewallet_amount


@transaction.atomic
def wallet_debit(user, amount, comment):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError('Amount must be greater than zero.')
    get_profile(user)
    profile = UserProfile.objects.select_for_update().get(user=user)
    if profile.ewallet_amount < amount:
        raise WalletError(f'Insufficient wallet balance (available Rs. {profile.ewallet_amount}).')
    profile.ewallet_amount -= amount
    profile.save(update_fields=['ewallet_amount'])
    WalletTransaction.objects.create(user=user, type='debit', amount=amount,
                                     balance=profile.ewallet_amount, comment=comment[:100])
    return profile.ewallet_amount
