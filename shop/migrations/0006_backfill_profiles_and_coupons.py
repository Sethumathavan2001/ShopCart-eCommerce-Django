from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('shop', 'UserProfile')
    Coupon = apps.get_model('shop', 'Coupon')

    for user in User.objects.filter(profile__isnull=True):
        UserProfile.objects.create(user=user)

    Coupon.objects.get_or_create(code='WELCOME10', defaults={
        'discount_type': 'percent', 'value': Decimal('10'), 'max_discount': Decimal('200'),
        'min_order_amount': Decimal('299'),
    })
    Coupon.objects.get_or_create(code='FLAT100', defaults={
        'discount_type': 'flat', 'value': Decimal('100'), 'min_order_amount': Decimal('999'),
    })


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0005_store_upgrade'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
