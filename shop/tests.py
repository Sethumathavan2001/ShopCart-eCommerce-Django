import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (Address, Cartlist, Catagory, Coupon, Favlist, Order, Products, Review, UserProfile,
                     WalletTransaction)


class ShopTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', 'alice@example.com', 'S3cure-pass!')
        self.other = User.objects.create_user('bob', 'bob@example.com', 'S3cure-pass!')
        self.cat = Catagory.objects.create(name='Electronics', description='Gadgets')
        self.product = Products.objects.create(category=self.cat, name='Headphones', vendor='ACME', quantity=5,
                                               orginal_price=1000, selling_price=800, description='Loud')
        self.cheap = Products.objects.create(category=self.cat, name='Cable', vendor='ACME', quantity=50,
                                             orginal_price=200, selling_price=150, description='USB-C')
        self.address = Address.objects.create(user=self.user, full_name='Alice', phone='9999999999',
                                              line1='1 Main St', city='Chennai', state='TN', pincode='600001',
                                              is_default=True)

    def login(self, user=None):
        self.client.force_login(user or self.user)

    def post_json(self, url, data):
        return self.client.post(url, json.dumps(data), content_type='application/json')


class ProfileTests(ShopTestCase):
    def test_profile_created_for_new_users(self):
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())


class CatalogueTests(ShopTestCase):
    def test_public_pages_render(self):
        for name in ['home', 'shop', 'collection', 'about', 'faq', 'contact', 'login', 'register']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(self.client.get(reverse('collectionview', args=[self.cat.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('productdetail', args=[self.product.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('policy', args=['terms'])).status_code, 200)

    def test_hidden_product_is_404(self):
        self.product.status = True
        self.product.save()
        self.assertEqual(self.client.get(reverse('productdetail', args=[self.product.id])).status_code, 404)

    def test_search_filter_and_sort(self):
        res = self.client.get(reverse('shop'), {'q': 'head'})
        self.assertContains(res, 'Headphones')
        self.assertNotContains(res, 'USB-C')
        res = self.client.get(reverse('shop'), {'max_price': 200, 'sort': 'price_high'})
        self.assertEqual([p.name for p in res.context['products']], ['Cable'])

    def test_search_suggest(self):
        data = self.client.get(reverse('search_suggest'), {'q': 'cab'}).json()
        self.assertEqual(data['results'][0]['name'], 'Cable')


class CartTests(ShopTestCase):
    def test_add_requires_login(self):
        res = self.post_json(reverse('addtocart'), {'pid': self.product.id, 'product_q': 1})
        self.assertEqual(res.status_code, 401)

    def test_add_merges_and_caps_at_stock(self):
        self.login()
        self.post_json(reverse('addtocart'), {'pid': self.product.id, 'product_q': 3})
        res = self.post_json(reverse('addtocart'), {'pid': self.product.id, 'product_q': 3})
        self.assertEqual(res.json()['cart_count'], 5)
        self.assertEqual(Cartlist.objects.get(user=self.user).quantity, 5)

    def test_update_and_remove_only_own_items(self):
        item = Cartlist.objects.create(user=self.other, product=self.product, quantity=1)
        self.login()
        self.assertEqual(self.post_json(reverse('update_cart', args=[item.id]), {'quantity': 2}).status_code, 404)
        self.client.post(reverse('removecart', args=[item.id]))
        self.assertTrue(Cartlist.objects.filter(id=item.id).exists())

    def test_update_quantity_returns_totals(self):
        self.login()
        item = Cartlist.objects.create(user=self.user, product=self.cheap, quantity=1)
        data = self.post_json(reverse('update_cart', args=[item.id]), {'quantity': 2}).json()
        self.assertEqual(data['quantity'], 2)
        self.assertEqual(Decimal(data['subtotal']), Decimal('300'))
        self.assertEqual(Decimal(data['shipping']), Decimal('40'))

    def test_coupon(self):
        Coupon.objects.create(code='SAVE10', discount_type='percent', value=10, min_order_amount=500)
        self.login()
        Cartlist.objects.create(user=self.user, product=self.product, quantity=1)
        self.client.post(reverse('apply_coupon'), {'code': 'save10'})
        res = self.client.get(reverse('cart'))
        self.assertEqual(res.context['coupon_discount'], Decimal('80.00'))
        self.assertEqual(res.context['total'], Decimal('720.00'))

    def test_coupon_minimum_not_met(self):
        Coupon.objects.create(code='BIG', discount_type='flat', value=100, min_order_amount=5000)
        self.login()
        Cartlist.objects.create(user=self.user, product=self.product, quantity=1)
        self.client.post(reverse('apply_coupon'), {'code': 'BIG'})
        self.assertIsNone(self.client.session.get('coupon_code'))


class WishlistTests(ShopTestCase):
    def test_toggle(self):
        self.login()
        self.assertTrue(self.post_json(reverse('addtofav'), {'pid': self.product.id}).json()['in_wishlist'])
        self.assertFalse(self.post_json(reverse('addtofav'), {'pid': self.product.id}).json()['in_wishlist'])

    def test_move_to_cart(self):
        self.login()
        fav = Favlist.objects.create(user=self.user, product=self.product)
        self.client.post(reverse('move_to_cart', args=[fav.id]))
        self.assertFalse(Favlist.objects.filter(id=fav.id).exists())
        self.assertTrue(Cartlist.objects.filter(user=self.user, product=self.product).exists())


class CheckoutTests(ShopTestCase):
    def test_cod_checkout_creates_order_and_reduces_stock(self):
        self.login()
        Cartlist.objects.create(user=self.user, product=self.product, quantity=2)
        res = self.client.post(reverse('checkout'), {'address_id': self.address.id, 'payment_method': 'cod'})
        order = Order.objects.get(user=self.user)
        self.assertRedirects(res, reverse('order_success', args=[order.order_number]))
        self.assertEqual(order.total, Decimal('1600'))
        self.assertEqual(order.status, 'confirmed')
        self.assertEqual(order.items.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 3)
        self.assertFalse(Cartlist.objects.filter(user=self.user).exists())

    def test_checkout_with_new_address(self):
        self.login()
        Cartlist.objects.create(user=self.user, product=self.cheap, quantity=1)
        self.client.post(reverse('checkout'), {
            'address_id': 'new', 'payment_method': 'cod', 'full_name': 'Alice B', 'phone': '1234567890',
            'line1': '2 Side St', 'city': 'Madurai', 'state': 'TN', 'pincode': '625001', 'country': 'India'})
        order = Order.objects.get(user=self.user)
        self.assertIn('Madurai', order.shipping_address)
        self.assertEqual(order.shipping_charge, Decimal('40'))

    def test_insufficient_stock_blocks_order(self):
        self.login()
        Cartlist.objects.create(user=self.user, product=self.product, quantity=2)
        Products.objects.filter(id=self.product.id).update(quantity=1)
        self.client.post(reverse('checkout'), {'address_id': self.address.id, 'payment_method': 'cod'})
        self.assertFalse(Order.objects.exists())

    def test_wallet_payment_and_cancel_refund(self):
        self.login()
        UserProfile.objects.filter(user=self.user).update(ewallet_amount=1000)
        Cartlist.objects.create(user=self.user, product=self.product, quantity=1)
        self.client.post(reverse('checkout'), {'address_id': self.address.id, 'payment_method': 'wallet'})
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.payment_status, 'paid')
        self.assertEqual(UserProfile.objects.get(user=self.user).ewallet_amount, Decimal('200'))

        self.client.post(reverse('cancel_order', args=[order.order_number]))
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(order.payment_status, 'refunded')
        self.assertEqual(self.product.quantity, 5)
        self.assertEqual(UserProfile.objects.get(user=self.user).ewallet_amount, Decimal('1000'))

    def test_wallet_insufficient_balance(self):
        self.login()
        Cartlist.objects.create(user=self.user, product=self.product, quantity=1)
        self.client.post(reverse('checkout'), {'address_id': self.address.id, 'payment_method': 'wallet'})
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 5)  # transaction rolled back

    def test_cannot_view_other_users_order(self):
        order = Order.objects.create(user=self.other, shipping_address='x', phone='1', subtotal=1, total=1)
        self.login()
        self.assertEqual(self.client.get(reverse('order_detail', args=[order.order_number])).status_code, 404)

    def test_account_pages_render(self):
        self.login()
        order = Order.objects.create(user=self.user, shipping_address='x', phone='1', subtotal=1, total=1)
        for url in [reverse('account'), reverse('orders'), reverse('addresses'), reverse('address_add'),
                    reverse('change_password'), reverse('ewallet'), reverse('favorite'), reverse('cart'),
                    reverse('order_detail', args=[order.order_number]),
                    reverse('order_invoice', args=[order.order_number])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)


class WalletTests(ShopTestCase):
    def test_add_and_withdraw(self):
        self.login()
        self.assertTrue(self.post_json(reverse('add_ewallet_amount'), {'amount': '500'}).json()['success'])
        res = self.post_json(reverse('withdraw_ewallet_amount'), {'withdraw-amount': '200'}).json()
        self.assertEqual(Decimal(res['new_balance']), Decimal('300'))
        self.assertEqual(WalletTransaction.objects.filter(user=self.user).count(), 2)

    def test_no_overdraft_or_negative(self):
        self.login()
        self.assertFalse(self.post_json(reverse('withdraw_ewallet_amount'), {'withdraw-amount': '10'}).json()['success'])
        self.assertFalse(self.post_json(reverse('add_ewallet_amount'), {'amount': '-50'}).json()['success'])
        self.assertEqual(UserProfile.objects.get(user=self.user).ewallet_amount, 0)


class ReviewTests(ShopTestCase):
    def test_review_create_and_update(self):
        self.login()
        url = reverse('add_review', args=[self.product.id])
        self.client.post(url, {'rating': 4, 'title': 'Good', 'comment': 'Nice'})
        self.client.post(url, {'rating': 5, 'title': 'Great', 'comment': 'Love it'})
        self.assertEqual(Review.objects.get(user=self.user).rating, 5)
        self.assertEqual(self.product.avg_rating, 5)


class AuthTests(ShopTestCase):
    def test_register_logs_in(self):
        res = self.client.post(reverse('register'), {
            'username': 'carol', 'email': 'carol@example.com',
            'password1': 'Very-strong-pass1', 'password2': 'Very-strong-pass1'})
        self.assertRedirects(res, reverse('home'))
        self.assertTrue(UserProfile.objects.filter(user__username='carol').exists())

    def test_login_with_email(self):
        res = self.client.post(reverse('login'), {'user': 'alice@example.com', 'password': 'S3cure-pass!'})
        self.assertRedirects(res, reverse('home'))

    def test_login_next_is_safe(self):
        res = self.client.post(reverse('login'), {'user': 'alice', 'password': 'S3cure-pass!',
                                                  'next': 'https://evil.example.com/'})
        self.assertRedirects(res, reverse('home'))


class StudioTests(ShopTestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user('staffer', 'staff@example.com', 'S3cure-pass!', is_staff=True)

    def test_hidden_from_customers_and_guests(self):
        for url in [reverse('studio'), reverse('studio_products'), reverse('studio_product_add'),
                    reverse('studio_categories')]:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.login()
        self.assertEqual(self.client.get(reverse('studio')).status_code, 404)
        self.assertNotContains(self.client.get(reverse('home')), reverse('studio'))

    def test_staff_sees_nav_link_and_pages(self):
        self.login(self.staff)
        self.assertContains(self.client.get(reverse('home')), reverse('studio'))
        for url in [reverse('studio'), reverse('studio_products'), reverse('studio_product_add'),
                    reverse('studio_product_edit', args=[self.product.id]), reverse('studio_categories'),
                    reverse('studio_category_add'), reverse('studio_category_edit', args=[self.cat.id])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def _image(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = io.BytesIO()
        img = Image.new('RGB', (300, 200), 'white')
        img.paste((200, 30, 30), (100, 50, 200, 150))
        img.save(buf, 'PNG')
        return SimpleUploadedFile('red box.png', buf.getvalue(), content_type='image/png')

    def test_add_product_with_processed_image(self):
        import shutil, tempfile
        from django.test import override_settings
        media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=media):
                self.login(self.staff)
                res = self.client.post(reverse('studio_product_add'), {
                    'name': 'Red Box', 'category': self.cat.id, 'vendor': 'BoxCo', 'sku': 'RB-1',
                    'description': 'A red box', 'selling_price': '499', 'orginal_price': '599', 'quantity': '12',
                    'process_image': 'on', 'product_image': self._image()})
                self.assertRedirects(res, reverse('studio_products'))
                p = Products.objects.get(name='Red Box')
                self.assertTrue(p.product_image.name.endswith('.jpg'))
                from PIL import Image
                with Image.open(p.product_image.path) as im:
                    self.assertEqual(im.size[0], im.size[1])  # squared
        finally:
            shutil.rmtree(media, ignore_errors=True)

    def test_validation(self):
        self.login(self.staff)
        res = self.client.post(reverse('studio_product_add'), {
            'name': 'Bad', 'category': self.cat.id, 'vendor': 'X', 'description': 'x',
            'selling_price': '500', 'orginal_price': '100', 'quantity': '1'})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Products.objects.filter(name='Bad').exists())

    def test_quick_update_and_bulk(self):
        self.login(self.staff)
        self.client.post(reverse('studio_product_quick', args=[self.product.id]), {'quantity': '42'})
        self.client.post(reverse('studio_product_bulk'), {'ids': [self.product.id, self.cheap.id], 'action': 'hide'})
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 42)
        self.assertTrue(self.product.status)
        self.assertTrue(Products.objects.get(id=self.cheap.id).status)

    def test_category_with_products_cannot_be_deleted(self):
        self.login(self.staff)
        self.client.post(reverse('studio_category_delete', args=[self.cat.id]))
        self.assertTrue(Catagory.objects.filter(id=self.cat.id).exists())


class CatalogCleaningTests(TestCase):
    def test_clean_title_and_brand(self):
        from shop.management.commands.prepare_catalog import brand_from, clean_title, unique_title
        raw = ('Soulflower Lavender Bath Salt for Body & Foot Spa, Calming, Relaxing | Pure & Natural')
        self.assertEqual(clean_title(raw), 'Soulflower Lavender Bath Salt for Body & Foot Spa')
        self.assertEqual(brand_from('amazon basics High-Speed Hdmi Cable,6 Feet'), 'Amazon Basics')
        self.assertEqual(brand_from('RN Toys Newboto Toddler Rocker'), 'RN Toys')
        taken = {'amazon basics high-speed hdmi cable'}
        self.assertEqual(unique_title('Amazon Basics High-Speed HDMI Cable, 3 Feet (Black)', taken),
                         'Amazon Basics High-Speed HDMI Cable - 3 Feet')


class CatalogFixtureTests(TestCase):
    fixtures = ['catalog']

    def test_fixture_loads_a_full_store(self):
        self.assertEqual(Catagory.objects.count(), 5)
        self.assertGreater(Products.objects.count(), 400)
        self.assertTrue(Coupon.objects.filter(code='WELCOME10').exists())
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)
