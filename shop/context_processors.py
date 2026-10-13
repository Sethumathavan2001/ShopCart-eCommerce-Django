from django.db.models import Count, Q, Sum

from .models import Cartlist, Catagory, Favlist


def shop_context(request):
    ctx = {
        'nav_categories': Catagory.objects.filter(status=False).annotate(
            product_count=Count('products', filter=Q(products__status=False))),
        'cart_count': 0,
        'wishlist_count': 0,
        'wishlist_ids': set(),
    }
    if request.user.is_authenticated:
        ctx['cart_count'] = Cartlist.objects.filter(user=request.user).aggregate(n=Sum('quantity'))['n'] or 0
        ids = set(Favlist.objects.filter(user=request.user).values_list('product_id', flat=True))
        ctx['wishlist_ids'] = ids
        ctx['wishlist_count'] = len(ids)
    return ctx
