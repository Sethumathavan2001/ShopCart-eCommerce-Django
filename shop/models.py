import datetime
import os
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg
from django.urls import reverse
from django.utils import timezone


def getfile(instance, filename):
    # Colons are not allowed in Windows filenames, so keep the timestamp digits only
    now = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    return os.path.join('uploads', f"{now}{filename}")


class Catagory(models.Model):
    name = models.CharField(max_length=150)
    image = models.ImageField(upload_to=getfile, null=True, blank=True)
    description = models.TextField(max_length=150)
    status = models.BooleanField(default=False, help_text='0-show,1-Hidden')
    icon = models.CharField(max_length=40, default='bi-grid', help_text='Bootstrap icon class, e.g. bi-basket')
    color = models.CharField(max_length=7, default='#4f46e5', help_text='Accent colour (hex), e.g. #16a34a')
    tagline = models.CharField(max_length=80, blank=True, help_text='Short headline used on the home page banner')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse('collectionview', args=[self.id])


class Products(models.Model):
    category = models.ForeignKey(Catagory, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=150)
    vendor = models.CharField('Brand', max_length=150)
    sku = models.CharField('SKU', max_length=40, blank=True)
    product_image = models.ImageField(upload_to=getfile, null=True, blank=True)
    quantity = models.IntegerField()
    orginal_price = models.FloatField()
    selling_price = models.FloatField()
    description = models.TextField(max_length=500)
    status = models.BooleanField(default=False, help_text='0-show,1-Hidden')
    trending = models.BooleanField(default=False, help_text='0-show,1-Trending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse('productdetail', args=[self.id])

    @property
    def discount_percent(self):
        if self.orginal_price and self.orginal_price > self.selling_price:
            return round((self.orginal_price - self.selling_price) / self.orginal_price * 100)
        return 0

    @property
    def in_stock(self):
        return self.quantity > 0

    @property
    def price(self):
        return Decimal(str(self.selling_price))

    @property
    def avg_rating(self):
        # Use the annotated value when the queryset provides it
        if hasattr(self, 'rating_avg'):
            return round(self.rating_avg or 0, 1)
        return round(self.reviews.aggregate(a=Avg('rating'))['a'] or 0, 1)


class Favlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey(Products, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Wishlist item'
        unique_together = ('user', 'product')
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.user} - {self.product}"


class Cartlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cart_items')
    product = models.ForeignKey(Products, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Cart item'
        unique_together = ('user', 'product')
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.user} - {self.product} x {self.quantity}"

    @property
    def line_total(self):
        return self.product.price * self.quantity

    @property
    def line_mrp(self):
        return Decimal(str(self.product.orginal_price)) * self.quantity


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    ewallet_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    phone = models.CharField(max_length=15, blank=True)
    avatar = models.ImageField(upload_to=getfile, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - eWallet: {self.ewallet_amount}"


class WalletTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance = models.DecimalField(max_digits=10, decimal_places=2)  # Balance after transaction
    comment = models.CharField(max_length=100, default="NA")

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.type.capitalize()} of {self.amount} on {self.date}'


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    line1 = models.CharField('Address line 1', max_length=255)
    line2 = models.CharField('Address line 2', max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default='India')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Addresses'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.full_name}, {self.city}"

    def as_text(self):
        parts = [self.full_name, self.line1, self.line2,
                 f"{self.city}, {self.state} - {self.pincode}", self.country, f"Phone: {self.phone}"]
        return "\n".join(p for p in parts if p)

    def save(self, *args, **kwargs):
        # Only one default address per user
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Coupon(models.Model):
    DISCOUNT_TYPES = [('percent', 'Percentage'), ('flat', 'Flat amount')]
    code = models.CharField(max_length=30, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPES, default='percent')
    value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                       help_text='Cap for percentage coupons (optional)')
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text='Total uses allowed (optional)')
    used_count = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        super().save(*args, **kwargs)

    def check_valid(self, subtotal):
        """Return (ok, message)."""
        now = timezone.now()
        if not self.active:
            return False, 'This coupon is no longer active.'
        if self.valid_from and now < self.valid_from:
            return False, 'This coupon is not active yet.'
        if self.valid_to and now > self.valid_to:
            return False, 'This coupon has expired.'
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False, 'This coupon has reached its usage limit.'
        if subtotal < self.min_order_amount:
            return False, f'Minimum order amount for this coupon is Rs. {self.min_order_amount}.'
        return True, 'Coupon applied.'

    def discount_for(self, subtotal):
        if self.discount_type == 'percent':
            discount = subtotal * self.value / Decimal('100')
            if self.max_discount:
                discount = min(discount, self.max_discount)
        else:
            discount = self.value
        return min(discount, subtotal).quantize(Decimal('0.01'))


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out for delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_METHODS = [
        ('cod', 'Cash on Delivery'),
        ('wallet', 'eWallet'),
        ('online', 'Online Payment'),
    ]
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]
    # Steps shown in the tracking timeline
    TRACKING_STEPS = ['pending', 'confirmed', 'shipped', 'out_for_delivery', 'delivered']

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    shipping_address = models.TextField()
    phone = models.CharField(max_length=15)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default='cod')
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default='pending')
    payment_reference = models.CharField(max_length=100, blank=True,
                                         help_text='Gateway transaction id (for online payments)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = 'OD' + timezone.now().strftime('%y%m%d') + uuid.uuid4().hex[:6].upper()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('order_detail', args=[self.order_number])

    @property
    def can_cancel(self):
        return self.status in ('pending', 'confirmed')

    @property
    def item_count(self):
        return sum(i.quantity for i in self.items.all())

    def tracking(self):
        """List of (label, done) for the status timeline."""
        if self.status == 'cancelled':
            return []
        current = self.TRACKING_STEPS.index(self.status)
        labels = dict(self.STATUS_CHOICES)
        return [(labels[s], i <= current) for i, s in enumerate(self.TRACKING_STEPS)]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Products, on_delete=models.SET_NULL, null=True)
    # Snapshot of the product at the time of ordering
    name = models.CharField(max_length=150)
    product_image = models.ImageField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.name} x {self.quantity}"

    @property
    def line_total(self):
        return self.price * self.quantity


class Review(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField(blank=True)
    verified_purchase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product} - {self.rating}★ by {self.user}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=150)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject} ({self.email})"


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
