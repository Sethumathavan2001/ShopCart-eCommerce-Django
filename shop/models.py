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

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    ewallet_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.user.username} - eWallet: {self.ewallet_amount}"
    
class WalletTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)  # Timestamp of the transaction
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)  # Transaction type (credit or debit)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # Amount of money for the transaction
    balance = models.DecimalField(max_digits=10, decimal_places=2)  # Current balance after transaction
    comment = models.CharField(max_length=100,default="NA")
    def __str__(self):
        return f'{self.type.capitalize()} of {self.amount} on {self.date}'