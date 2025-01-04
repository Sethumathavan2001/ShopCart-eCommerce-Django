import csv
import os
from django.core.management.base import BaseCommand
from shop.models import Products, Catagory
from django.conf import settings
from django.core.files import File

class Command(BaseCommand):
    help = 'Import categories and products from CSV files into the database'

    def handle(self, *args, **kwargs):
        # Define the paths to your CSV files
        categories_csv_path = os.path.join(settings.BASE_DIR,'shop','data', 'shop_catagory.csv')  # Path to your category CSV
        products_csv_path = os.path.join(settings.BASE_DIR,'shop','data', 'shop_products.csv')  # Replace with actual product CSV path

        # Import categories from CSV
        with open(categories_csv_path, mode='r', encoding='utf-8') as category_file:
            category_reader = csv.DictReader(category_file)
            
            for row in category_reader:
                    category = Catagory(
                        # name=category,
                        name=row['name'],
                        image=row['image'],
                        description=row['description'],
                        status=int(row['status']) == 1
                    )
                    
                    category.save()
                    self.stdout.write(self.style.SUCCESS(f"Created product: {category.name}"))
        
        # Import products from CSV
        with open(products_csv_path, mode='r', encoding='utf-8') as product_file:
            product_reader = csv.DictReader(product_file)
            
            for row in product_reader:
                # Get category object (ensure the category exists, otherwise create it)
                category = Catagory.objects.filter(name=row['category']).first()
                
                # Create the product
                product = Products(
                    category=category,
                    name=row['name'],
                    vendor=row['vendor'],
                    product_image=row['product_image'],  # Ensure the image path is correct
                    quantity=int(row['quantity']),
                    orginal_price=float(row['orginal_price']),
                    selling_price=float(row['selling_price']),
                    description=row['description'],
                    status=int(row['status']) == 1,  # Convert 'True'/'False' to Boolean
                    trending=int(row['trending']) == 1,  # Convert 'True'/'False' to Boolean
                )
                
                product.save()
                self.stdout.write(self.style.SUCCESS(f"Created product: {product.name}"))
        
        self.stdout.write(self.style.SUCCESS('Successfully imported categories and products from CSV'))
