from django.db import models
from django.contrib.auth.models import User
import datetime,os
# Create your models here.
def getfile(request, filename):
    now = datetime.datetime.now().strftime('%Y%m%d%H:%M:%S')
    new_file = f"{now}{filename}"
    return os.path.join('uploads',new_file)
class Catagory(models.Model):
    name = models.CharField(max_length=150,null=False,blank=False)
    image = models.ImageField(upload_to=getfile,null=True,blank=True)
    description = models.TextField(max_length=150,null=False,blank=False)
    status = models.BooleanField(default=False,help_text='0-show,1-Hidden')
    #trending = models.BooleanField(default=False,help_text='0-show,1-Trending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self) -> str:
        return self.name

class Products(models.Model):
    category = models.ForeignKey(Catagory,on_delete=models.CASCADE)
    name = models.CharField(max_length=150,null=False,blank=False)
    vendor = models.CharField(max_length=150,null=False,blank=False)
    product_image = models.ImageField(upload_to=getfile,null=True,blank=True)
    quantity = models.IntegerField(null=False,blank=False)
    orginal_price = models.FloatField(null=False,blank=False)
    selling_price = models.FloatField(null=False,blank=False)
    description = models.TextField(max_length=500,null=False,blank=False)
    status = models.BooleanField(default=False,help_text='0-show,1-Hidden')
    trending = models.BooleanField(default=False,help_text='0-show,1-Trending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self) -> str:
        return self.name
class Favlist(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    category = models.ForeignKey(Catagory,on_delete=models.CASCADE)
    product = models.ForeignKey(Products,on_delete=models.CASCADE)
    name = models.CharField(max_length=150,null=False,blank=False)
    product_image = models.ImageField(upload_to=getfile,null=True,blank=True)
    orginal_price = models.FloatField(null=False,blank=False)
    selling_price = models.FloatField(null=False,blank=False)
    status = models.BooleanField(default=False,help_text='0-show,1-Hidden')
    trending = models.BooleanField(default=False,help_text='0-show,1-Trending')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self) -> str:
        return self.name
     
class Cartlist(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    category = models.ForeignKey(Catagory,on_delete=models.CASCADE)
    product = models.ForeignKey(Products,on_delete=models.CASCADE)
    name = models.CharField(max_length=150,null=False,blank=False)
    product_image = models.ImageField(upload_to=getfile,null=True,blank=True)
    quantity = models.IntegerField(null=False,blank=False)
    orginal_price = models.FloatField(null=False,blank=False)
    selling_price = models.FloatField(null=False,blank=False)
    status = models.BooleanField(default=False,help_text='0-show,1-Hidden')
    trending = models.BooleanField(default=False,help_text='0-show,1-Trending')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self) -> str:
        return self.name

