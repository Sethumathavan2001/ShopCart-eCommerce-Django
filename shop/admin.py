from django.contrib import admin
from .models import Catagory,Products,UserProfile
# Register your models here.
admin.site.register(Catagory)
admin.site.register(Products)
admin.site.register(UserProfile)