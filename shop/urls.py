from django.contrib.auth import views as auth_views
from django.urls import path

from . import studio, views

urlpatterns = [
    # Catalogue
    path('', views.home, name='home'),
    path('shop', views.shop, name='shop'),
    path('collection', views.collection, name='collection'),
    path('collectionview/<int:catid>', views.collectionview, name='collectionview'),
    path('productdetail/<int:pid>', views.productdetail, name='productdetail'),
    path('productdetail/<int:pid>/review', views.add_review, name='add_review'),
    path('productdetail/<int:pid>/review/delete', views.delete_review, name='delete_review'),
    path('search/suggest', views.search_suggest, name='search_suggest'),

    # Cart & wishlist
    path('cart', views.cart_page, name='cart'),
    path('addtocart', views.addtocart, name='addtocart'),
    path('cart/update/<int:cartid>', views.update_cart, name='update_cart'),
    path('removecart/<int:cartid>', views.removecart, name='removecart'),
    path('cart/coupon', views.apply_coupon, name='apply_coupon'),
    path('cart/coupon/remove', views.remove_coupon, name='remove_coupon'),
    path('buyproduct/<int:productid>', views.buyproduct, name='buyproduct'),
    path('favorite', views.favorite, name='favorite'),
    path('addtofav', views.addtofav, name='addtofav'),
    path('removefav/<int:cartid>', views.removefav, name='removefav'),
    path('favorite/move-to-cart/<int:favid>', views.move_to_cart, name='move_to_cart'),

    # Checkout & orders
    path('checkout', views.checkout, name='checkout'),
    path('payment/<str:order_number>', views.payment_start, name='payment_start'),
    path('orders', views.orders, name='orders'),
    path('orders/<str:order_number>', views.order_detail, name='order_detail'),
    path('orders/<str:order_number>/success', views.order_success, name='order_success'),
    path('orders/<str:order_number>/invoice', views.order_invoice, name='order_invoice'),
    path('orders/<str:order_number>/cancel', views.cancel_order, name='cancel_order'),
    path('orders/<str:order_number>/reorder', views.reorder, name='reorder'),

    # Auth & account
    path('login', views.login_form, name='login'),
    path('register', views.register, name='register'),
    path('logout', views.logout_page, name='logout'),
    path('account', views.account, name='account'),
    path('account/password', views.change_password, name='change_password'),
    path('account/addresses', views.addresses, name='addresses'),
    path('account/addresses/add', views.address_edit, name='address_add'),
    path('account/addresses/<int:address_id>/edit', views.address_edit, name='address_edit'),
    path('account/addresses/<int:address_id>/delete', views.address_delete, name='address_delete'),
    path('password-reset', auth_views.PasswordResetView.as_view(
        template_name='auth/password_reset.html',
        email_template_name='auth/password_reset_email.txt',
        subject_template_name='auth/password_reset_subject.txt'), name='password_reset'),
    path('password-reset/done', auth_views.PasswordResetDoneView.as_view(
        template_name='auth/password_reset_done.html'), name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>', auth_views.PasswordResetConfirmView.as_view(
        template_name='auth/password_reset_confirm.html'), name='password_reset_confirm'),
    path('password-reset/complete', auth_views.PasswordResetCompleteView.as_view(
        template_name='auth/password_reset_complete.html'), name='password_reset_complete'),

    # eWallet
    path('ewallet', views.ewallet, name='ewallet'),
    path('add-ewallet-amount/', views.add_ewallet_amount, name='add_ewallet_amount'),
    path('withdraw-ewallet-amount/', views.withdraw_ewallet_amount, name='withdraw_ewallet_amount'),

    # Seller Studio (staff only, 404 for everyone else)
    path('studio/', studio.dashboard, name='studio'),
    path('studio/products', studio.product_list, name='studio_products'),
    path('studio/products/add', studio.product_edit, name='studio_product_add'),
    path('studio/products/<int:pid>/edit', studio.product_edit, name='studio_product_edit'),
    path('studio/products/<int:pid>/delete', studio.product_delete, name='studio_product_delete'),
    path('studio/products/<int:pid>/quick', studio.product_quick_update, name='studio_product_quick'),
    path('studio/products/bulk', studio.product_bulk, name='studio_product_bulk'),
    path('studio/categories', studio.category_list, name='studio_categories'),
    path('studio/categories/add', studio.category_edit, name='studio_category_add'),
    path('studio/categories/<int:cid>/edit', studio.category_edit, name='studio_category_edit'),
    path('studio/categories/<int:cid>/delete', studio.category_delete, name='studio_category_delete'),

    # Info pages
    path('about', views.about, name='about'),
    path('faq', views.faq, name='faq'),
    path('contact', views.contact, name='contact'),
    path('policy/<slug:slug>', views.policy, name='policy'),
    path('newsletter', views.newsletter, name='newsletter'),
]
