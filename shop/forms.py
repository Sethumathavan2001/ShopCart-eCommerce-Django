from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Address, Catagory, ContactMessage, Products, Review, UserProfile


class NewUserForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=False,
                                 widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}))
    last_name = forms.CharField(max_length=150, required=False,
                                widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}))
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    password1 = forms.CharField(label='Password',
                                widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Create a password'}))
    password2 = forms.CharField(label='Confirm password',
                                widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repeat the password'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email


class BootstrapModelForm(forms.ModelForm):
    """Adds Bootstrap classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault('class', 'form-select')
            else:
                widget.attrs.setdefault('class', 'form-control')


class UserUpdateForm(BootstrapModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class ProfileUpdateForm(BootstrapModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'avatar']


class AddressForm(BootstrapModelForm):
    class Meta:
        model = Address
        fields = ['full_name', 'phone', 'line1', 'line2', 'city', 'state', 'pincode', 'country', 'is_default']
        labels = {'is_default': 'Make this my default address'}


class ReviewForm(BootstrapModelForm):
    rating = forms.TypedChoiceField(choices=[(i, f'{i} star{"s" if i > 1 else ""}') for i in range(5, 0, -1)],
                                    coerce=int)

    class Meta:
        model = Review
        fields = ['rating', 'title', 'comment']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Summarise your experience'}),
            'comment': forms.Textarea(attrs={'rows': 4, 'placeholder': 'What did you like or dislike?'}),
        }


class ContactForm(BootstrapModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'subject', 'message']
        widgets = {'message': forms.Textarea(attrs={'rows': 5})}


class ProductForm(BootstrapModelForm):
    process_image = forms.BooleanField(
        required=False, initial=True, label='Auto-optimise image',
        help_text='Trim white borders and centre the product on a square white canvas.')

    class Meta:
        model = Products
        fields = ['name', 'category', 'vendor', 'sku', 'description', 'selling_price', 'orginal_price',
                  'quantity', 'product_image', 'trending', 'status']
        labels = {
            'name': 'Product name', 'orginal_price': 'MRP (original price)', 'selling_price': 'Selling price',
            'quantity': 'Stock quantity', 'product_image': 'Product image', 'trending': 'Feature as trending',
            'status': 'Hide from store',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6}),
            'product_image': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'selling_price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}),
            'orginal_price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}),
            'quantity': forms.NumberInput(attrs={'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].empty_label = 'Choose a category'

    def clean(self):
        data = super().clean()
        selling, mrp = data.get('selling_price'), data.get('orginal_price')
        if selling is not None and selling <= 0:
            self.add_error('selling_price', 'Price must be greater than zero.')
        if selling is not None and mrp is not None and mrp < selling:
            self.add_error('orginal_price', 'MRP cannot be lower than the selling price.')
        if data.get('quantity') is not None and data['quantity'] < 0:
            self.add_error('quantity', 'Stock cannot be negative.')
        return data


class CategoryForm(BootstrapModelForm):
    class Meta:
        model = Catagory
        fields = ['name', 'tagline', 'description', 'icon', 'color', 'image', 'status']
        labels = {'status': 'Hide from store', 'icon': 'Icon', 'color': 'Accent colour'}
        widgets = {'description': forms.Textarea(attrs={'rows': 3}),
                   'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
                   'image': forms.ClearableFileInput(attrs={'accept': 'image/*'})}
