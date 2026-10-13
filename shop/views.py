import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Avg, Count, F, Max, Min, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (AddressForm, ContactForm, NewUserForm, ProfileUpdateForm, ReviewForm,
                    UserUpdateForm)
from .models import (Address, Cartlist, Catagory, Coupon, Favlist, NewsletterSubscriber, Order,
                     OrderItem, Products, Review, WalletTransaction)
from .services import (COUPON_SESSION_KEY, MAX_QTY_PER_ITEM, WalletError, cart_summary,
                       get_profile, wallet_credit, wallet_debit)

PRODUCTS_PER_PAGE = 24
RECENTLY_VIEWED_KEY = 'recently_viewed'

SORT_OPTIONS = {
    'newest': ('Newest first', ['-created_at']),
    'popular': ('Popularity', ['-sold', '-created_at']),
    'price_low': ('Price: Low to High', ['selling_price']),
    'price_high': ('Price: High to Low', ['-selling_price']),
    'discount': ('Biggest discount', ['-discount_amount']),
    'rating': ('Customer rating', ['-rating_avg', '-rating_count']),
}


def visible_products():
    return (Products.objects.filter(status=False, category__status=False)
            .select_related('category')
            .annotate(rating_avg=Avg('reviews__rating'), rating_count=Count('reviews', distinct=True)))


def json_body(request):
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return {}


def safe_next(request, default='home'):
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return default


# --------------------------------------------------------------------------- catalogue

def home(request):
    products = visible_products()
    deals = sorted(products.filter(quantity__gt=0)[:200], key=lambda p: p.discount_percent, reverse=True)[:8]
    context = {
        'trend': products.filter(trending=True)[:12],
        'new_arrivals': products[:8],
        'deals': deals,
        'categories': Catagory.objects.filter(status=False).annotate(
            product_count=Count('products', filter=Q(products__status=False))),
        'recently_viewed': _recently_viewed(request),
        'top_brands': (products.values('vendor').annotate(n=Count('id', distinct=True))
                       .filter(n__gte=2).order_by('-n', 'vendor')[:12]),
        'deal_ends': timezone.localtime().replace(hour=23, minute=59, second=59),
    }
    return render(request, 'home.html', context)


def collection(request):
    category = Catagory.objects.filter(status=False).annotate(
        product_count=Count('products', filter=Q(products__status=False)))
    return render(request, 'collection.html', {'category': category})


def shop(request, catid=None):
    products = visible_products().annotate(
        sold=Coalesce(Subquery(OrderItem.objects.filter(product=OuterRef('pk')).values('product')
                               .annotate(s=Sum('quantity')).values('s')), 0),
        discount_amount=F('orginal_price') - F('selling_price'),
    )
    current_category = None
    if catid is not None:
        current_category = get_object_or_404(Catagory, id=catid, status=False)
        products = products.filter(category=current_category)
    elif request.GET.get('category'):
        current_category = Catagory.objects.filter(id=request.GET['category'], status=False).first()
        if current_category:
            products = products.filter(category=current_category)

    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q) |
                                   Q(vendor__icontains=q) | Q(category__name__icontains=q))

    price_bounds = products.aggregate(lo=Min('selling_price'), hi=Max('selling_price'))
    min_price = _to_float(request.GET.get('min_price'))
    max_price = _to_float(request.GET.get('max_price'))
    if min_price is not None:
        products = products.filter(selling_price__gte=min_price)
    if max_price is not None:
        products = products.filter(selling_price__lte=max_price)
    if request.GET.get('in_stock'):
        products = products.filter(quantity__gt=0)
    if request.GET.get('on_sale'):
        products = products.filter(orginal_price__gt=F('selling_price'))
    min_rating = _to_float(request.GET.get('rating'))
    if min_rating:
        products = products.filter(rating_avg__gte=min_rating)

    sort = request.GET.get('sort', 'newest')
    if sort not in SORT_OPTIONS:
        sort = 'newest'
    products = products.order_by(*SORT_OPTIONS[sort][1])

    page = Paginator(products, PRODUCTS_PER_PAGE).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    context = {
        'products': page,
        'page_obj': page,
        'current_category': current_category,
        'q': q,
        'sort': sort,
        'sort_options': [(k, v[0]) for k, v in SORT_OPTIONS.items()],
        'min_price': request.GET.get('min_price', ''),
        'max_price': request.GET.get('max_price', ''),
        'price_bounds': price_bounds,
        'querystring': params.urlencode(),
        'categories': Catagory.objects.filter(status=False),
    }
    return render(request, 'productslist.html', context)


def collectionview(request, catid):
    return shop(request, catid=catid)


def search_suggest(request):
    q = request.GET.get('q', '').strip()
    results = []
    if len(q) >= 2:
        for p in visible_products().filter(Q(name__icontains=q) | Q(category__name__icontains=q))[:8]:
            results.append({
                'id': p.id,
                'name': p.name,
                'price': p.selling_price,
                'category': p.category.name,
                'image': p.product_image.url if p.product_image else '',
                'url': p.get_absolute_url(),
            })
    return JsonResponse({'results': results})


def productdetail(request, pid):
    product = get_object_or_404(visible_products(), id=pid)
    reviews = product.reviews.select_related('user')
    rating_breakdown = []
    total_reviews = reviews.count()
    counts = dict(reviews.values_list('rating').annotate(n=Count('id')))
    for star in range(5, 0, -1):
        n = counts.get(star, 0)
        rating_breakdown.append((star, n, round(n * 100 / total_reviews) if total_reviews else 0))

    user_review = None
    review_form = None
    if request.user.is_authenticated:
        user_review = reviews.filter(user=request.user).first()
        review_form = ReviewForm(instance=user_review)

    related = visible_products().filter(category=product.category).exclude(id=product.id).order_by('?')[:8]

    # Track recently viewed products in the session
    viewed = [i for i in request.session.get(RECENTLY_VIEWED_KEY, []) if i != product.id]
    request.session[RECENTLY_VIEWED_KEY] = [product.id] + viewed[:11]

    context = {
        'product': product,
        'offer': product.discount_percent,
        'reviews': reviews[:20],
        'total_reviews': total_reviews,
        'rating_breakdown': rating_breakdown,
        'user_review': user_review,
        'review_form': review_form,
        'related': related,
        'in_cart': request.user.is_authenticated and Cartlist.objects.filter(
            user=request.user, product=product).exists(),
        'max_qty': min(product.quantity, MAX_QTY_PER_ITEM),
        'delivery_date': _delivery_date(),
        'offers': Coupon.objects.filter(active=True).order_by('min_order_amount')[:3],
        'highlights': _highlights(product),
        'intro': product.description.split('\n\nHighlights:')[0],
    }
    return render(request, 'productdetails.html', context)


@login_required
@require_POST
def add_review(request, pid):
    product = get_object_or_404(Products, id=pid, status=False)
    existing = Review.objects.filter(product=product, user=request.user).first()
    form = ReviewForm(request.POST, instance=existing)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        review.user = request.user
        review.verified_purchase = OrderItem.objects.filter(
            order__user=request.user, product=product, order__status='delivered').exists()
        review.save()
        messages.success(request, 'Thanks! Your review has been saved.')
    else:
        messages.error(request, 'Please choose a rating between 1 and 5.')
    return redirect(f"{product.get_absolute_url()}#reviews")


@login_required
@require_POST
def delete_review(request, pid):
    Review.objects.filter(product_id=pid, user=request.user).delete()
    messages.info(request, 'Your review was deleted.')
    return redirect(reverse('productdetail', args=[pid]) + '#reviews')


# --------------------------------------------------------------------------- cart

@login_required
def cart_page(request):
    summary = cart_summary(request)
    if summary['coupon_error']:
        messages.warning(request, summary['coupon_error'])
    return render(request, 'cart_page.html', summary)


@require_POST
def addtocart(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'Please login to add items to your cart', 'login_required': True}, status=401)
    data = json_body(request)
    product = Products.objects.filter(id=data.get('pid'), status=False).first()
    if not product:
        return JsonResponse({'status': 'Product unavailable'}, status=404)
    if product.quantity < 1:
        return JsonResponse({'status': 'Sorry, this product is out of stock'}, status=400)
    try:
        qty = max(1, int(data.get('product_q', 1)))
    except (TypeError, ValueError):
        qty = 1

    limit = min(product.quantity, MAX_QTY_PER_ITEM)
    item, created = Cartlist.objects.get_or_create(user=request.user, product=product,
                                                   defaults={'quantity': min(qty, limit)})
    if created:
        msg = 'Added to cart'
    else:
        item.quantity = min(item.quantity + qty, limit)
        item.save(update_fields=['quantity'])
        msg = f'Cart updated (quantity {item.quantity})'
    count = Cartlist.objects.filter(user=request.user).aggregate(n=Sum('quantity'))['n'] or 0
    return JsonResponse({'status': msg, 'success': True, 'cart_count': count})


@login_required
@require_POST
def update_cart(request, cartid):
    item = get_object_or_404(Cartlist, id=cartid, user=request.user)
    data = json_body(request)
    try:
        qty = int(data.get('quantity', request.POST.get('quantity', item.quantity)))
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid quantity'}, status=400)

    if qty < 1:
        item.delete()
    else:
        item.quantity = min(qty, item.product.quantity, MAX_QTY_PER_ITEM)
        item.save(update_fields=['quantity'])

    summary = cart_summary(request)
    line = next((i for i in summary['items'] if i.id == cartid), None)
    return JsonResponse({
        'success': True,
        'removed': line is None,
        'quantity': line.quantity if line else 0,
        'line_total': str(line.line_total) if line else '0',
        'cart_count': summary['item_count'],
        'subtotal': str(summary['subtotal']),
        'mrp_total': str(summary['mrp_total']),
        'product_savings': str(summary['product_savings']),
        'coupon_discount': str(summary['coupon_discount']),
        'shipping': str(summary['shipping']),
        'free_shipping_gap': str(summary['free_shipping_gap']),
        'total': str(summary['total']),
        'empty': not summary['items'],
    })


@login_required
@require_POST
def removecart(request, cartid):
    Cartlist.objects.filter(id=cartid, user=request.user).delete()
    messages.info(request, 'Item removed from cart.')
    return redirect('cart')


@login_required
@require_POST
def apply_coupon(request):
    code = request.POST.get('code', '').strip().upper()
    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        messages.error(request, 'Invalid coupon code.')
        return redirect(safe_next(request, 'cart'))
    summary = cart_summary(request)
    ok, msg = coupon.check_valid(summary['subtotal'])
    if ok:
        request.session[COUPON_SESSION_KEY] = coupon.code
        messages.success(request, f'Coupon {coupon.code} applied — you save Rs. {coupon.discount_for(summary["subtotal"])}')
    else:
        messages.error(request, msg)
    return redirect(safe_next(request, 'cart'))


@login_required
@require_POST
def remove_coupon(request):
    request.session.pop(COUPON_SESSION_KEY, None)
    messages.info(request, 'Coupon removed.')
    return redirect(safe_next(request, 'cart'))


@login_required
@require_POST
def buyproduct(request, productid):
    """Buy now: put the product in the cart with the chosen quantity and go to checkout."""
    product = get_object_or_404(Products, id=productid, status=False)
    if product.quantity < 1:
        messages.error(request, 'Sorry, this product is out of stock.')
        return redirect(product.get_absolute_url())
    try:
        qty = max(1, int(request.POST.get('quantity', 1)))
    except ValueError:
        qty = 1
    qty = min(qty, product.quantity, MAX_QTY_PER_ITEM)
    Cartlist.objects.update_or_create(user=request.user, product=product, defaults={'quantity': qty})
    return redirect('checkout')


# --------------------------------------------------------------------------- wishlist

@login_required
def favorite(request):
    fav_list = Favlist.objects.filter(user=request.user).select_related('product', 'product__category')
    return render(request, 'favorite.html', {'fav_list': fav_list})


@require_POST
def addtofav(request):
    """Toggle a product in the wishlist."""
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'Please login to use your wishlist', 'login_required': True}, status=401)
    data = json_body(request)
    product = Products.objects.filter(id=data.get('pid'), status=False).first()
    if not product:
        return JsonResponse({'status': 'Product unavailable'}, status=404)
    fav, created = Favlist.objects.get_or_create(user=request.user, product=product)
    if not created:
        fav.delete()
    count = Favlist.objects.filter(user=request.user).count()
    return JsonResponse({
        'success': True,
        'in_wishlist': created,
        'status': 'Added to wishlist' if created else 'Removed from wishlist',
        'wishlist_count': count,
    })


@login_required
@require_POST
def removefav(request, cartid):
    Favlist.objects.filter(id=cartid, user=request.user).delete()
    messages.info(request, 'Removed from wishlist.')
    return redirect('favorite')


@login_required
@require_POST
def move_to_cart(request, favid):
    fav = get_object_or_404(Favlist, id=favid, user=request.user)
    if fav.product.quantity < 1 or fav.product.status:
        messages.error(request, f'{fav.product.name} is currently out of stock.')
        return redirect('favorite')
    item, created = Cartlist.objects.get_or_create(user=request.user, product=fav.product)
    fav.delete()
    messages.success(request, 'Moved to cart.')
    return redirect('favorite')


# --------------------------------------------------------------------------- checkout & orders

@login_required
def checkout(request):
    summary = cart_summary(request)
    if not summary['items']:
        messages.info(request, 'Your cart is empty.')
        return redirect('cart')

    addresses = Address.objects.filter(user=request.user)
    address_form = AddressForm(initial={
        'full_name': request.user.get_full_name(),
        'phone': get_profile(request.user).phone,
        'is_default': not addresses.exists(),
    })
    wallet_balance = get_profile(request.user).ewallet_amount

    if request.method == 'POST':
        # A new address can be entered right on the checkout page
        address = None
        if request.POST.get('address_id') == 'new':
            address_form = AddressForm(request.POST)
            if address_form.is_valid():
                address = address_form.save(commit=False)
                address.user = request.user
                address.save()
        else:
            address = addresses.filter(id=request.POST.get('address_id')).first()

        payment_method = request.POST.get('payment_method', 'cod')
        if address is None:
            messages.error(request, 'Please select or add a delivery address.')
        elif payment_method not in dict(Order.PAYMENT_METHODS):
            messages.error(request, 'Please choose a payment method.')
        elif payment_method == 'online' and not settings.ONLINE_PAYMENT_ENABLED:
            messages.error(request, 'Online payment is not available yet. Please choose another method.')
        else:
            try:
                order = _place_order(request, address, payment_method, request.POST.get('note', ''))
            except (ValueError, WalletError) as exc:
                messages.error(request, str(exc))
            else:
                if payment_method == 'online':
                    return redirect('payment_start', order_number=order.order_number)
                messages.success(request, f'Order {order.order_number} placed successfully!')
                return redirect('order_success', order_number=order.order_number)

    context = dict(summary, addresses=addresses, address_form=address_form,
                   wallet_balance=wallet_balance,
                   online_payment_enabled=settings.ONLINE_PAYMENT_ENABLED)
    return render(request, 'checkout.html', context)


@transaction.atomic
def _place_order(request, address, payment_method, note):
    summary = cart_summary(request)
    items = summary['items']
    if not items:
        raise ValueError('Your cart is empty.')

    # Lock product rows so two orders can't oversell the same stock
    products = {p.id: p for p in Products.objects.select_for_update().filter(id__in=[i.product_id for i in items])}
    for item in items:
        product = products[item.product_id]
        if product.status:
            raise ValueError(f'{product.name} is no longer available. Please remove it from your cart.')
        if product.quantity < item.quantity:
            raise ValueError(f'Only {product.quantity} unit(s) of {product.name} left in stock. '
                             f'Please update your cart.')

    order = Order.objects.create(
        user=request.user,
        shipping_address=address.as_text(),
        phone=address.phone,
        subtotal=summary['subtotal'],
        discount=summary['coupon_discount'],
        shipping_charge=summary['shipping'],
        total=summary['total'],
        coupon=summary['coupon'],
        payment_method=payment_method,
        note=note[:500],
    )
    for item in items:
        product = products[item.product_id]
        OrderItem.objects.create(order=order, product=product, name=product.name,
                                 product_image=product.product_image.name if product.product_image else None,
                                 price=product.price, quantity=item.quantity)
        product.quantity -= item.quantity
        product.save(update_fields=['quantity'])

    if payment_method == 'wallet':
        wallet_debit(request.user, order.total, f'Payment for order {order.order_number}')
        order.payment_status = 'paid'
        order.status = 'confirmed'
        order.save(update_fields=['payment_status', 'status'])
    elif payment_method == 'cod':
        order.status = 'confirmed'
        order.save(update_fields=['status'])

    if summary['coupon']:
        Coupon.objects.filter(id=summary['coupon'].id).update(used_count=F('used_count') + 1)
    request.session.pop(COUPON_SESSION_KEY, None)
    Cartlist.objects.filter(user=request.user).delete()
    return order


@login_required
def payment_start(request, order_number):
    """
    Hook for an online payment gateway (Razorpay / Stripe / PayU ...).

    Create the gateway order here using `order.total`, render the gateway's checkout,
    and on a verified success callback set:
        order.payment_status = 'paid'; order.status = 'confirmed'; order.payment_reference = <gateway id>
    """
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if order.payment_status == 'paid':
        return redirect('order_success', order_number=order.order_number)
    return render(request, 'payment.html', {'order': order})


@login_required
def order_success(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    return render(request, 'order_success.html', {'order': order})


@login_required
def orders(request):
    order_list = Order.objects.filter(user=request.user).prefetch_related('items')
    status = request.GET.get('status')
    if status in dict(Order.STATUS_CHOICES):
        order_list = order_list.filter(status=status)
    page = Paginator(order_list, 10).get_page(request.GET.get('page'))
    return render(request, 'orders.html', {'orders': page, 'page_obj': page, 'status': status,
                                           'status_choices': Order.STATUS_CHOICES})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related('items__product'),
                              order_number=order_number, user=request.user)
    return render(request, 'order_page.html', {'order': order})


@login_required
def order_invoice(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related('items'), order_number=order_number, user=request.user)
    return render(request, 'invoice.html', {'order': order})


@login_required
@require_POST
@transaction.atomic
def cancel_order(request, order_number):
    order = get_object_or_404(Order.objects.select_for_update(), order_number=order_number, user=request.user)
    if not order.can_cancel:
        messages.error(request, 'This order can no longer be cancelled.')
        return redirect(order.get_absolute_url())

    for item in order.items.select_related('product'):
        if item.product_id:
            Products.objects.filter(id=item.product_id).update(quantity=F('quantity') + item.quantity)

    order.status = 'cancelled'
    if order.payment_status == 'paid' and order.payment_method == 'wallet':
        wallet_credit(request.user, order.total, f'Refund for order {order.order_number}')
        order.payment_status = 'refunded'
        messages.success(request, f'Order cancelled. Rs. {order.total} has been refunded to your eWallet.')
    else:
        messages.success(request, 'Order cancelled.')
    order.save(update_fields=['status', 'payment_status'])
    return redirect(order.get_absolute_url())


@login_required
@require_POST
def reorder(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    added = 0
    for item in order.items.select_related('product'):
        p = item.product
        if p and not p.status and p.quantity > 0:
            Cartlist.objects.update_or_create(user=request.user, product=p,
                                              defaults={'quantity': min(item.quantity, p.quantity, MAX_QTY_PER_ITEM)})
            added += 1
    if added:
        messages.success(request, f'{added} item(s) added to your cart.')
    else:
        messages.warning(request, 'None of the items in this order are available right now.')
    return redirect('cart')


# --------------------------------------------------------------------------- auth & account

def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = NewUserForm()
    if request.method == 'POST':
        form = NewUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to ShopCart, {user.username}! Your account is ready.')
            return redirect('home')
        messages.error(request, 'Please correct the errors below.')
    return render(request, 'register.html', {'form': form})


def login_form(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        user = request.POST.get('user', '').strip()
        pwd = request.POST.get('password')
        # Allow logging in with either username or email
        if '@' in user:
            match = User.objects.filter(email__iexact=user).first()
            if match:
                user = match.username
        log_auth = authenticate(request, username=user, password=pwd)
        if log_auth is not None:
            login(request, log_auth)
            if not request.POST.get('remember'):
                request.session.set_expiry(0)
            messages.success(request, f'Welcome back, {log_auth.first_name or log_auth.username}!')
            return redirect(safe_next(request, 'home'))
        messages.error(request, 'Invalid username or password.')
    return render(request, 'login.html', {'next': request.GET.get('next', '')})


def logout_page(request):
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required
def account(request):
    profile = get_profile(request.user)
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Profile updated.')
            return redirect('account')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=profile)

    stats = Order.objects.filter(user=request.user).exclude(status='cancelled').aggregate(
        count=Count('id'), spent=Sum('total'))
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'profile': profile,
        'order_count': stats['count'] or 0,
        'total_spent': stats['spent'] or 0,
        'recent_orders': Order.objects.filter(user=request.user)[:3],
        'address_count': Address.objects.filter(user=request.user).count(),
    }
    return render(request, 'account.html', context)


@login_required
def change_password(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    for field in form.fields.values():
        field.widget.attrs['class'] = 'form-control'
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, 'Your password was changed.')
        return redirect('account')
    return render(request, 'change_password.html', {'form': form})


@login_required
def addresses(request):
    return render(request, 'addresses.html', {'addresses': Address.objects.filter(user=request.user)})


@login_required
def address_edit(request, address_id=None):
    instance = get_object_or_404(Address, id=address_id, user=request.user) if address_id else None
    form = AddressForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        if not Address.objects.filter(user=request.user).exclude(pk=address.pk).exists():
            address.is_default = True
        address.save()
        messages.success(request, 'Address saved.')
        return redirect(safe_next(request, 'addresses'))
    return render(request, 'address_form.html', {'form': form, 'instance': instance})


@login_required
@require_POST
def address_delete(request, address_id):
    Address.objects.filter(id=address_id, user=request.user).delete()
    messages.info(request, 'Address deleted.')
    return redirect('addresses')


# --------------------------------------------------------------------------- wallet

@login_required
def ewallet(request):
    profile = get_profile(request.user)
    history = WalletTransaction.objects.filter(user=request.user)
    totals = history.values('type').annotate(total=Sum('amount'))
    totals = {t['type']: t['total'] for t in totals}
    page = Paginator(history, 15).get_page(request.GET.get('page'))
    return render(request, 'ewallet.html', {
        'inr': profile.ewallet_amount,
        'wallet_history': page,
        'page_obj': page,
        'total_credit': totals.get('credit', 0),
        'total_debit': totals.get('debit', 0),
    })


def _wallet_amount(request, key):
    data = json_body(request)
    try:
        amount = Decimal(str(data.get(key, ''))).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0 or amount > settings.WALLET_MAX_TRANSACTION:
        return None
    return amount


@login_required
@require_POST
def add_ewallet_amount(request):
    # NOTE: once a payment gateway is integrated, credit the wallet only after the payment succeeds.
    amount = _wallet_amount(request, 'amount')
    if amount is None:
        return JsonResponse({'success': False,
                             'message': f'Enter an amount between 1 and {settings.WALLET_MAX_TRANSACTION}.'})
    balance = wallet_credit(request.user, amount, 'Amount Credited')
    return JsonResponse({'success': True, 'new_balance': str(balance)})


@login_required
@require_POST
def withdraw_ewallet_amount(request):
    amount = _wallet_amount(request, 'withdraw-amount')
    if amount is None:
        return JsonResponse({'success': False,
                             'message': f'Enter an amount between 1 and {settings.WALLET_MAX_TRANSACTION}.'})
    try:
        balance = wallet_debit(request.user, amount, 'Amount Withdrawn')
    except WalletError as exc:
        return JsonResponse({'success': False, 'message': str(exc)})
    return JsonResponse({'success': True, 'new_balance': str(balance)})


# --------------------------------------------------------------------------- static pages

def about(request):
    return render(request, 'pages/about.html')


def faq(request):
    return render(request, 'pages/faq.html')


def policy(request, slug):
    pages = {
        'terms': 'Terms of Use',
        'privacy': 'Privacy Policy',
        'shipping': 'Shipping & Delivery',
        'returns': 'Returns & Refunds',
    }
    if slug not in pages:
        raise Http404
    return render(request, 'pages/policy.html', {'slug': slug, 'title': pages[slug]})


def contact(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {'name': request.user.get_full_name() or request.user.username, 'email': request.user.email}
    form = ContactForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Thanks for reaching out! We will get back to you within 24 hours.')
        return redirect('contact')
    return render(request, 'pages/contact.html', {'form': form})


@require_POST
def newsletter(request):
    email = request.POST.get('email', '').strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        messages.error(request, 'Please enter a valid email address.')
    else:
        NewsletterSubscriber.objects.get_or_create(email=email)
        messages.success(request, 'You are subscribed! Watch your inbox for exclusive deals.')
    return redirect(safe_next(request, 'home'))


# --------------------------------------------------------------------------- helpers

def _to_float(value):
    try:
        return float(value) if value not in (None, '') else None
    except ValueError:
        return None


def _highlights(product):
    """Bullet lines from the description, skipping any that merely repeat the product name."""
    name = product.name.lower()[:30]
    lines = (line.lstrip('• ').strip() for line in product.description.splitlines() if line.startswith('•'))
    return [h for h in lines if h and not h.lower().startswith(name)]


def _delivery_date(days=3):
    """Estimated delivery date, skipping Sundays."""
    day = timezone.localdate()
    while days:
        day += timedelta(days=1)
        if day.weekday() != 6:
            days -= 1
    return day


def _recently_viewed(request):
    ids = request.session.get(RECENTLY_VIEWED_KEY, [])
    if not ids:
        return []
    by_id = {p.id: p for p in visible_products().filter(id__in=ids)}
    return [by_id[i] for i in ids if i in by_id][:8]


def page_not_found(request, exception):
    return render(request, '404.html', status=404)
