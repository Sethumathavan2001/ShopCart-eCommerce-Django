"""Seller Studio: a staff-only area for managing the catalogue from the storefront."""
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .forms import CategoryForm, ProductForm
from .imaging import square_product_image
from .models import Catagory, Order, Products
from .views import safe_next

LOW_STOCK = 5

CATEGORY_ICONS = ['bi-grid', 'bi-basket2', 'bi-stars', 'bi-cpu', 'bi-heart-pulse', 'bi-balloon-heart',
                  'bi-phone', 'bi-laptop', 'bi-headphones', 'bi-watch', 'bi-camera', 'bi-controller',
                  'bi-house', 'bi-lamp', 'bi-cup-hot', 'bi-egg-fried', 'bi-flower1', 'bi-gem', 'bi-bag',
                  'bi-handbag', 'bi-book', 'bi-brush', 'bi-bicycle', 'bi-tools', 'bi-capsule', 'bi-gift']


def staff_required(view):
    """Hidden area: anyone who isn't staff gets a plain 404."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            raise Http404
        return view(request, *args, **kwargs)
    return wrapper


def _save_image(instance, field_name, upload, process, filename):
    if not upload:
        return
    field = getattr(instance, field_name)
    if process:
        try:
            field.save(f'{slugify(filename)[:50] or "image"}.jpg', ContentFile(square_product_image(upload)),
                       save=False)
            return
        except Exception:
            upload.seek(0)  # not an image Pillow can read: keep the original file
    field.save(upload.name, upload, save=False)


@staff_required
def dashboard(request):
    products = Products.objects.all()
    today = timezone.localdate()
    week_ago = timezone.now() - timedelta(days=7)
    live_orders = Order.objects.exclude(status='cancelled')
    context = {
        'stats': {
            'products': products.count(),
            'live': products.filter(status=False).count(),
            'low_stock': products.filter(quantity__gt=0, quantity__lte=LOW_STOCK).count(),
            'out_of_stock': products.filter(quantity__lte=0).count(),
            'orders_today': Order.objects.filter(created_at__date=today).count(),
            'revenue_week': live_orders.filter(created_at__gte=week_ago).aggregate(s=Sum('total'))['s'] or 0,
            'pending': Order.objects.filter(status__in=['pending', 'confirmed']).count(),
        },
        'recent_orders': Order.objects.select_related('user')[:6],
        'low_stock_items': products.filter(quantity__lte=LOW_STOCK).select_related('category').order_by('quantity')[:8],
        'categories': Catagory.objects.annotate(n=Count('products')).order_by('-n'),
        'studio_active': 'dashboard',
    }
    return render(request, 'studio/dashboard.html', context)


@staff_required
def product_list(request):
    products = Products.objects.select_related('category')
    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(vendor__icontains=q) | Q(sku__icontains=q))
    if request.GET.get('category'):
        products = products.filter(category_id=request.GET['category'])
    stock = request.GET.get('stock')
    if stock == 'out':
        products = products.filter(quantity__lte=0)
    elif stock == 'low':
        products = products.filter(quantity__gt=0, quantity__lte=LOW_STOCK)
    visibility = request.GET.get('visibility')
    if visibility == 'hidden':
        products = products.filter(status=True)
    elif visibility == 'live':
        products = products.filter(status=False)
    if request.GET.get('trending'):
        products = products.filter(trending=True)

    sort = request.GET.get('sort', '-created_at')
    allowed = {'-created_at', 'name', 'selling_price', '-selling_price', 'quantity', '-quantity'}
    products = products.order_by(sort if sort in allowed else '-created_at')

    page = Paginator(products, 25).get_page(request.GET.get('page'))
    return render(request, 'studio/product_list.html', {
        'products': page, 'page_obj': page, 'q': q, 'sort': sort,
        'categories': Catagory.objects.all(), 'low_stock': LOW_STOCK, 'studio_active': 'products',
    })


@staff_required
def product_edit(request, pid=None):
    product = get_object_or_404(Products, id=pid) if pid else None
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            obj = form.save(commit=False)
            upload = request.FILES.get('product_image')
            if upload:
                _save_image(obj, 'product_image', upload, form.cleaned_data.get('process_image'), obj.name)
            obj.save()
            messages.success(request, f'"{obj.name}" was {"updated" if product else "added to the store"}.')
            if 'save_add' in request.POST:
                return redirect('studio_product_add')
            return redirect('studio_products')
        messages.error(request, 'Please fix the highlighted fields.')
    else:
        initial = {}
        if not product and request.GET.get('category'):
            initial['category'] = request.GET['category']
        form = ProductForm(instance=product, initial=initial)
    return render(request, 'studio/product_form.html', {
        'form': form, 'product': product, 'studio_active': 'products' if product else 'add'})


@staff_required
@require_POST
def product_delete(request, pid):
    product = get_object_or_404(Products, id=pid)
    name = product.name
    product.delete()
    messages.success(request, f'"{name}" was deleted.')
    return redirect('studio_products')


@staff_required
@require_POST
def product_bulk(request):
    ids = request.POST.getlist('ids')
    action = request.POST.get('action')
    qs = Products.objects.filter(id__in=ids)
    updates = {
        'show': {'status': False}, 'hide': {'status': True},
        'feature': {'trending': True}, 'unfeature': {'trending': False},
    }
    if action in updates:
        n = qs.update(**updates[action])
        messages.success(request, f'{n} product(s) updated.')
    elif action == 'delete':
        n = qs.count()
        qs.delete()
        messages.success(request, f'{n} product(s) deleted.')
    else:
        messages.error(request, 'Choose an action and at least one product.')
    return redirect(safe_next(request, 'studio_products'))


@staff_required
@require_POST
def product_quick_update(request, pid):
    """Inline stock / price / visibility edits from the product table."""
    product = get_object_or_404(Products, id=pid)
    try:
        if 'quantity' in request.POST:
            product.quantity = max(0, int(request.POST['quantity']))
        if 'selling_price' in request.POST:
            price = float(request.POST['selling_price'])
            if price <= 0:
                raise ValueError
            product.selling_price = price
            product.orginal_price = max(product.orginal_price, price)
    except ValueError:
        messages.error(request, 'Invalid value.')
    else:
        if 'toggle_status' in request.POST:
            product.status = not product.status
        if 'toggle_trending' in request.POST:
            product.trending = not product.trending
        product.save()
        messages.success(request, f'"{product.name}" updated.')
    return redirect(safe_next(request, 'studio_products'))


@staff_required
def category_list(request):
    categories = Catagory.objects.annotate(n=Count('products'), live=Count('products', filter=Q(products__status=False)))
    return render(request, 'studio/category_list.html', {'categories': categories, 'studio_active': 'categories'})


@staff_required
def category_edit(request, cid=None):
    category = get_object_or_404(Catagory, id=cid) if cid else None
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        upload = request.FILES.get('image')
        if upload:
            _save_image(obj, 'image', upload, False, obj.name)
        obj.save()
        messages.success(request, f'Category "{obj.name}" saved.')
        return redirect('studio_categories')
    return render(request, 'studio/category_form.html', {
        'form': form, 'category': category, 'icons': CATEGORY_ICONS, 'studio_active': 'categories'})


@staff_required
@require_POST
def category_delete(request, cid):
    category = get_object_or_404(Catagory, id=cid)
    if category.products.exists():
        messages.error(request, f'"{category.name}" still has products. Move or delete them first.')
    else:
        category.delete()
        messages.success(request, 'Category deleted.')
    return redirect('studio_categories')
