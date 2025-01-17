from django.urls import path
from . import views
urlpatterns = [
    path('removecart/<str:cartid>', views.removecart,name='removecart'),
    path('removefav/<str:cartid>', views.removefav,name='removefav'),
    path('addtocart', views.addtocart,name='addtocart'),
    path('', views.home,name='home'),
    path('login', views.login_form,name='login'),
    path('register', views.register,name='register'),
    path('collection', views.collection,name='collection'),
    path('collectionview/<str:catid>', views.collectionview,name='collectionview'),
    path('productdetail/<str:pid>', views.productdetail,name='productdetail'),
    path('logout', views.logout_page,name='logout'),
    path('cart', views.cart_page,name='cart'),
    path('favorite', views.favorite,name='favorite'),
    path('addtofav', views.addtofav,name='addtofav'),
    path('ewallet', views.ewallet,name='ewallet'),
    path('add-ewallet-amount/', views.add_ewallet_amount, name='add_ewallet_amount'),

]