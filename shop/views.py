from django.shortcuts import render,redirect
from .models import Catagory,Products,Cartlist,Favlist
from django.contrib import messages
from django.contrib.auth import authenticate,login,logout
from django.http import JsonResponse
from .forms import NewUserForm
import json
def home(request):
    trending_products = Products.objects.filter(trending=1)
    return render(request,'home.html',{'trend':trending_products})

def cart_page(request):
    if request.user.is_authenticated:
        cart_list = Cartlist.objects.filter(user = request.user)
        print(cart_list)
        return render(request,'cart_page.html',{'cart_list':cart_list})

    else:
        return redirect('/')

def removecart(request,cartid):
        cartp = Cartlist.objects.get(id=cartid)
        if cartp:
            cartp.delete()
            return redirect('/cart')
        else:
            return redirect('/cart')
    
def removefav(request,cartid):
        cartp = Favlist.objects.get(id=cartid)
        if cartp:
            cartp.delete()
            return redirect('/favorite')
        else:
            return redirect('/favorite')
        
def addtocart(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        if request.user.is_authenticated:
            data = json.load(request)
            product = Products.objects.get(id = data['pid'],status = 0)
            print(product)
            if product:
                cart = Cartlist.objects.filter(user = request.user,product_id = data['pid'])
                if cart:
                    return JsonResponse({'status':'Already In cart'},status=200) 
                else:
                    Cartlist.objects.create(user=request.user,product_id=data['pid'],category_id = product.category.id,name = product.name,product_image=product.product_image,
                                            quantity=data['product_q'],orginal_price=product.orginal_price,selling_price=product.selling_price,
                                            status=product.status,trending = product.trending)
                    return JsonResponse({'status':'Product Added'},status=200)
            else:
                return JsonResponse({'status':'Product Unavailable'},status=200)
        else:
            return JsonResponse({'status':'Please Login'},status=200)
    else:
        return JsonResponse({'status':'Invalid Access'},status=200)
    
def register(request):
    form = NewUserForm()
    if request.method == 'POST':
        form = NewUserForm(request.POST)
        print(form)
        if form.is_valid():
            form.save()
            messages.success(request,'Registerd Successfully')
            return redirect('/login')
        else:
            messages.error(request,'Invalid Form')
            return redirect('/collection')
    return render(request,'register.html',{'form':form})

def collection(request):
    category = Catagory.objects.filter(status=0)
    return render(request,'collection.html',{'category':category})

def collectionview(request,catid):
    if (Catagory.objects.filter(id = catid,status=0)):
        products = Products.objects.filter(category_id = catid,status=0)
        return render(request, 'productslist.html',{'products':products})
    else:
        return messages('Category Unavalible')
def productdetail(request,pid):
    product = Products.objects.get(id = pid)
    offerprice =round((product.orginal_price-product.selling_price)/product.orginal_price*100)
    return render(request, 'productdetails.html',{'product':product,'offer':offerprice})

def login_form(request):
    if request.method=='POST':
        user = request.POST.get('user')
        pwd = request.POST.get('password')
        log_auth = authenticate(request,username = user,password = pwd)
        if log_auth is not None:
            login(request,log_auth)
            return redirect('/')
        else:
            messages.error(request,"Invalid User Name and Password")
            return redirect('/login')
    return render(request,'login.html')

def logout_page(request):
    if request.user.is_authenticated:
        logout(request)
        return redirect('/')
    else:
        return redirect('/')
    
def favorite(request):
    if request.user.is_authenticated:
        fav_list = Favlist.objects.filter(user = request.user)
        return render(request,'favorite.html',{'fav_list':fav_list})
    else:
        return redirect('/')

def addtofav(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        if request.user.is_authenticated:
            data = json.load(request)
            product = Products.objects.get(id = data['pid'],status = 0)
            print(product)
            if product:
                cart = Favlist.objects.filter(user = request.user,product_id = data['pid'])
                if cart:
                    return JsonResponse({'status':'Already In Favorite'},status=200) 
                else:
                    Favlist.objects.create(user=request.user,product_id=data['pid'],category_id = product.category.id,name = product.name,product_image=product.product_image,
                                            orginal_price=product.orginal_price,selling_price=product.selling_price,
                                            status=product.status,trending = product.trending)
                    return JsonResponse({'status':'Product Added'},status=200)
            else:
                return JsonResponse({'status':'Product Unavailable'},status=200)
        else:
            return JsonResponse({'status':'Please Login'},status=200)
    else:
        return JsonResponse({'status':'Invalid Access'},status=200) 