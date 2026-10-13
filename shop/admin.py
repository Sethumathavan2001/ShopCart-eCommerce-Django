from django.contrib import admin, messages
from django.db.models import Count, F
from django.utils.html import format_html

from .models import (Address, Cartlist, Catagory, ContactMessage, Coupon, Favlist, NewsletterSubscriber,
                     Order, OrderItem, Products, Review, UserProfile, WalletTransaction)
from .services import wallet_credit


def thumb(image, size=48):
    if image:
        return format_html('<img src="{}" style="height:{}px;width:{}px;object-fit:contain;border-radius:6px;'
                           'background:#fff">', image.url, size, size)
    return '-'


@admin.register(Catagory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('preview', 'name', 'product_count', 'status', 'created_at')
    list_display_links = ('preview', 'name')
    list_editable = ('status',)
    search_fields = ('name',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count('products'))

    @admin.display(description='Image')
    def preview(self, obj):
        return thumb(obj.image)

    @admin.display(description='Products', ordering='n')
    def product_count(self, obj):
        return obj.n


class LowStockFilter(admin.SimpleListFilter):
    title = 'stock'
    parameter_name = 'stock'

    def lookups(self, request, model_admin):
        return [('out', 'Out of stock'), ('low', 'Low stock (≤ 5)'), ('in', 'In stock')]

    def queryset(self, request, queryset):
        if self.value() == 'out':
            return queryset.filter(quantity__lte=0)
        if self.value() == 'low':
            return queryset.filter(quantity__gt=0, quantity__lte=5)
        if self.value() == 'in':
            return queryset.filter(quantity__gt=0)
        return queryset


@admin.register(Products)
class ProductsAdmin(admin.ModelAdmin):
    list_display = ('preview', 'name', 'category', 'selling_price', 'orginal_price', 'discount',
                    'quantity', 'trending', 'status')
    list_display_links = ('preview', 'name')
    list_editable = ('selling_price', 'quantity', 'trending', 'status')
    list_filter = ('category', 'trending', 'status', LowStockFilter)
    search_fields = ('name', 'vendor', 'sku', 'description')
    list_per_page = 50
    actions = ['mark_trending', 'unmark_trending', 'hide_products', 'show_products']

    @admin.display(description='Image')
    def preview(self, obj):
        return thumb(obj.product_image)

    @admin.display(description='Off')
    def discount(self, obj):
        return f'{obj.discount_percent}%'

    @admin.action(description='Mark selected as trending')
    def mark_trending(self, request, queryset):
        queryset.update(trending=True)

    @admin.action(description='Remove selected from trending')
    def unmark_trending(self, request, queryset):
        queryset.update(trending=False)

    @admin.action(description='Hide selected products')
    def hide_products(self, request, queryset):
        queryset.update(status=True)

    @admin.action(description='Show selected products')
    def show_products(self, request, queryset):
        queryset.update(status=False)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('preview', 'product', 'name', 'price', 'quantity', 'line_total')
    fields = readonly_fields
    can_delete = False

    @admin.display(description='Image')
    def preview(self, obj):
        return thumb(obj.product_image, 40)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'total', 'payment_method', 'payment_badge', 'status_badge',
                    'created_at')
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('order_number', 'user__username', 'user__email', 'phone')
    readonly_fields = ('order_number', 'user', 'subtotal', 'discount', 'shipping_charge', 'total', 'coupon',
                       'created_at', 'updated_at')
    fieldsets = (
        ('Order', {'fields': ('order_number', 'user', 'status', 'created_at', 'updated_at')}),
        ('Payment', {'fields': ('payment_method', 'payment_status', 'payment_reference')}),
        ('Amounts', {'fields': ('subtotal', 'discount', 'coupon', 'shipping_charge', 'total')}),
        ('Delivery', {'fields': ('shipping_address', 'phone', 'note')}),
    )
    inlines = [OrderItemInline]
    date_hierarchy = 'created_at'
    actions = ['mark_confirmed', 'mark_shipped', 'mark_out_for_delivery', 'mark_delivered', 'cancel_and_refund']

    STATUS_COLORS = {'pending': '#f59e0b', 'confirmed': '#3b82f6', 'shipped': '#8b5cf6',
                     'out_for_delivery': '#06b6d4', 'delivered': '#16a34a', 'cancelled': '#dc2626'}

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px">{}</span>',
                           self.STATUS_COLORS.get(obj.status, '#666'), obj.get_status_display())

    @admin.display(description='Payment', ordering='payment_status')
    def payment_badge(self, obj):
        color = {'paid': '#16a34a', 'refunded': '#6b7280', 'failed': '#dc2626'}.get(obj.payment_status, '#f59e0b')
        return format_html('<span style="color:{};font-weight:600">{}</span>', color, obj.get_payment_status_display())

    def _set_status(self, request, queryset, status):
        n = queryset.exclude(status='cancelled').update(status=status)
        self.message_user(request, f'{n} order(s) updated.')

    @admin.action(description='Mark as confirmed')
    def mark_confirmed(self, request, queryset):
        self._set_status(request, queryset, 'confirmed')

    @admin.action(description='Mark as shipped')
    def mark_shipped(self, request, queryset):
        self._set_status(request, queryset, 'shipped')

    @admin.action(description='Mark as out for delivery')
    def mark_out_for_delivery(self, request, queryset):
        self._set_status(request, queryset, 'out_for_delivery')

    @admin.action(description='Mark as delivered (COD marked paid)')
    def mark_delivered(self, request, queryset):
        queryset = queryset.exclude(status='cancelled')
        queryset.filter(payment_method='cod').update(payment_status='paid')
        self._set_status(request, queryset, 'delivered')

    @admin.action(description='Cancel, restock and refund wallet payments')
    def cancel_and_refund(self, request, queryset):
        count = 0
        for order in queryset.exclude(status__in=['cancelled', 'delivered']):
            for item in order.items.all():
                if item.product_id:
                    Products.objects.filter(id=item.product_id).update(quantity=F('quantity') + item.quantity)
            if order.payment_status == 'paid' and order.payment_method == 'wallet':
                wallet_credit(order.user, order.total, f'Refund for order {order.order_number}')
                order.payment_status = 'refunded'
            order.status = 'cancelled'
            order.save()
            count += 1
        self.message_user(request, f'{count} order(s) cancelled.', messages.SUCCESS)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'value', 'min_order_amount', 'used_count', 'usage_limit',
                    'valid_to', 'active')
    list_editable = ('active',)
    list_filter = ('active', 'discount_type')
    search_fields = ('code',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'title', 'verified_purchase', 'created_at')
    list_filter = ('rating', 'verified_purchase')
    search_fields = ('product__name', 'user__username', 'title', 'comment')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'ewallet_amount')
    search_fields = ('user__username', 'user__email', 'phone')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'amount', 'balance', 'comment', 'date')
    list_filter = ('type', 'date')
    search_fields = ('user__username', 'comment')

    def has_change_permission(self, request, obj=None):
        return False  # Ledger entries are immutable


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'city', 'state', 'pincode', 'phone', 'is_default')
    search_fields = ('user__username', 'full_name', 'city', 'pincode', 'phone')


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'name', 'email', 'is_resolved', 'created_at')
    list_editable = ('is_resolved',)
    list_filter = ('is_resolved',)
    search_fields = ('name', 'email', 'subject', 'message')


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'created_at')
    search_fields = ('email',)


@admin.register(Cartlist)
class CartlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'quantity', 'created_at')
    search_fields = ('user__username', 'product__name')


@admin.register(Favlist)
class FavlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'created_at')
    search_fields = ('user__username', 'product__name')
