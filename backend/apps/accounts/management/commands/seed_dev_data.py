"""
Create demo farmers and buyers with locations for local development.

    python manage.py seed_dev_data
    python manage.py seed_dev_data --password "Something-Else-1"

Safe to run repeatedly (updates the same accounts). Refuses to run when
DEBUG is False unless --force is given.
"""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User
from apps.locations.models import Province, UserLocation

DEFAULT_PASSWORD = "Dev-Passw0rd-2026"

# (email, display_name, role, province, municipality, town, lat, lng, delivery areas)
SEED_USERS = [
    ("thandi.farmer@example.com", "Thandi's Vegetable Farm", Role.FARMER, Province.GAUTENG,
     "City of Johannesburg", "Johannesburg", "-26.204100", "28.047300", []),
    ("sipho.farmer@example.com", "Sipho Greens", Role.FARMER, Province.GAUTENG,
     "City of Johannesburg", "Soweto", "-26.267800", "27.858500", []),
    ("lerato.farmer@example.com", "Lerato Organics", Role.FARMER, Province.GAUTENG,
     "City of Tshwane", "Pretoria", "-25.747900", "28.229300", []),
    ("johan.farmer@example.com", "Benoni Potatoes", Role.FARMER, Province.GAUTENG,
     "Ekurhuleni", "Benoni", None, None, []),
    ("mpho.farmer@example.com", "Mpho's Tomatoes", Role.FARMER, Province.LIMPOPO,
     "Polokwane Local Municipality", "Polokwane", None, None, []),
    ("nomsa.farmer@example.com", "Midlands Fresh", Role.FARMER, Province.KWAZULU_NATAL,
     "Msunduzi", "Pietermaritzburg", "-29.616800", "30.392800", []),
    ("anele.farmer@example.com", "Boland Berries", Role.FARMER, Province.WESTERN_CAPE,
     "Stellenbosch", "Stellenbosch", None, None, []),
    ("chef.buyer@example.com", "Rosebank Bistro", Role.WHOLESALE_BUYER, Province.GAUTENG,
     "City of Johannesburg", "Rosebank", "-26.145800", "28.041900",
     [{"province": Province.GAUTENG, "municipality": "City of Johannesburg", "town": ""}]),
    ("fresh.buyer@example.com", "Tshwane FreshMart", Role.WHOLESALE_BUYER, Province.GAUTENG,
     "City of Tshwane", "Centurion", None, None,
     [{"province": Province.GAUTENG, "municipality": "City of Tshwane", "town": "Pretoria"},
      {"province": Province.GAUTENG, "municipality": "City of Tshwane", "town": "Centurion"}]),
    ("coast.buyer@example.com", "Coastal Produce Distributors", Role.WHOLESALE_BUYER, Province.KWAZULU_NATAL,
     "eThekwini", "Durban", "-29.858700", "31.021800",
     [{"province": Province.KWAZULU_NATAL, "municipality": "", "town": ""}]),
]


class Command(BaseCommand):
    help = "Create demo farmers and wholesale buyers with locations (some with GPS, some without)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for every seeded user.")
        parser.add_argument("--force", action="store_true", help="Allow running when DEBUG is False.")

    @transaction.atomic
    def handle(self, *args, password, force, **options):
        if not settings.DEBUG and not force:
            raise CommandError("Refusing to seed demo data with DEBUG=False. Use --force if you are sure.")

        created_count = 0
        for email, name, role, province, municipality, town, lat, lng, areas in SEED_USERS:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=password, role=role, display_name=name)
                created_count += 1
            else:
                user.display_name, user.role = name, role
                user.set_password(password)
                user.save()
            UserLocation.objects.update_or_create(
                user=user,
                defaults={
                    "province": province,
                    "municipality": municipality,
                    "town": town,
                    "latitude": Decimal(lat) if lat else None,
                    "longitude": Decimal(lng) if lng else None,
                    "preferred_delivery_areas": areas,
                },
            )
            gps = "GPS" if lat else "no GPS"
            self.stdout.write(f"  {role:<16} {email:<32} {town} ({gps})")

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(SEED_USERS)} users ({created_count} new). Password for all: {password}"
        ))
