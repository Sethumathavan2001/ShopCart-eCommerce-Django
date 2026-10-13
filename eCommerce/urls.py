from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'ShopCart Administration'
admin.site.site_title = 'ShopCart Admin'
admin.site.index_title = 'Store management'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('shop.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'shop.views.page_not_found'
