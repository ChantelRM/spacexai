"""
Create a realistic South African demo dataset for local development.

    python manage.py seed_dev_data
    python manage.py seed_dev_data --password "Something-Else-1"

Creates 8 farmers and 5 buyers across Gauteng, Limpopo, KwaZulu-Natal and
the Western Cape (some with GPS, some without), plus profiles, listings,
buyer requirements, orders in several states, a farmer group, a fertiliser
bulk purchase, a shared transport trip, equipment and storage, a shared
security arrangement and insurance information.

Safe to run repeatedly: demo accounts are updated in place and their demo
data is rebuilt. Refuses to run when DEBUG is False unless --force is given.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.locations.models import Province, UserLocation

DEFAULT_PASSWORD = "Dev-Passw0rd-2026"
G, L, K, W = Province.GAUTENG, Province.LIMPOPO, Province.KWAZULU_NATAL, Province.WESTERN_CAPE

# key: (email, display_name, role, province, municipality, town, lat, lng, delivery areas)
SEED_USERS = {
    "thandi": ("thandi.farmer@example.com", "Thandi's Vegetable Farm", Role.FARMER, G, "City of Johannesburg",
               "Johannesburg", "-26.204100", "28.047300", []),
    "sipho": ("sipho.farmer@example.com", "Sipho Greens", Role.FARMER, G, "City of Johannesburg", "Soweto",
              "-26.267800", "27.858500", []),
    "lerato": ("lerato.farmer@example.com", "Lerato Organics", Role.FARMER, G, "City of Tshwane", "Pretoria",
               "-25.747900", "28.229300", []),
    "johan": ("johan.farmer@example.com", "Benoni Potatoes", Role.FARMER, G, "Ekurhuleni", "Benoni", None, None, []),
    "mpho": ("mpho.farmer@example.com", "Mpho's Tomatoes", Role.FARMER, L, "Polokwane Local Municipality",
             "Polokwane", None, None, []),
    "nomsa": ("nomsa.farmer@example.com", "Midlands Fresh", Role.FARMER, K, "Msunduzi", "Pietermaritzburg",
              "-29.616800", "30.392800", []),
    "anele": ("anele.farmer@example.com", "Boland Berries", Role.FARMER, W, "Stellenbosch", "Stellenbosch",
              None, None, []),
    "kagiso": ("kagiso.farmer@example.com", "Kagiso Poultry & Eggs", Role.FARMER, G, "City of Johannesburg",
               "Soweto", None, None, []),
    "chef": ("chef.buyer@example.com", "Rosebank Bistro", Role.WHOLESALE_BUYER, G, "City of Johannesburg",
             "Rosebank", "-26.145800", "28.041900",
             [{"province": G, "municipality": "City of Johannesburg", "town": ""}]),
    "fresh": ("fresh.buyer@example.com", "Tshwane FreshMart", Role.WHOLESALE_BUYER, G, "City of Tshwane", "Centurion",
              None, None, [{"province": G, "municipality": "City of Tshwane", "town": ""}]),
    "coast": ("coast.buyer@example.com", "Coastal Produce Distributors", Role.WHOLESALE_BUYER, K, "eThekwini",
              "Durban", "-29.858700", "31.021800", [{"province": K, "municipality": "", "town": ""}]),
    "spaza": ("spaza.buyer@example.com", "Soweto Spaza Wholesalers", Role.WHOLESALE_BUYER, G, "City of Johannesburg",
              "Soweto", None, None, []),
    "jam": ("jam.buyer@example.com", "Cape Jam Processors", Role.WHOLESALE_BUYER, W, "City of Cape Town",
            "Cape Town", "-33.924900", "18.424100", [{"province": W, "municipality": "", "town": ""}]),
}

FARM_PROFILES = {
    "thandi": ("Thandi's Vegetable Farm", ["Tomatoes", "Spinach", "Onions"], "6.5", True),
    "sipho": ("Sipho Greens", ["Spinach", "Cabbage", "Tomatoes"], "2.0", False),
    "lerato": ("Lerato Organics", ["Tomatoes", "Butternut"], "4.0", True),
    "johan": ("Benoni Potatoes", ["Potatoes"], "20.0", False),
    "mpho": ("Mpho's Tomatoes", ["Tomatoes"], "12.0", False),
    "nomsa": ("Midlands Fresh", ["Cabbage", "Potatoes"], "8.0", False),
    "anele": ("Boland Berries", ["Strawberries"], "3.0", False),
    "kagiso": ("Kagiso Poultry & Eggs", ["Eggs"], "1.5", False),
}

BUYER_PROFILES = {
    "chef": ("Rosebank Bistro", "RESTAURANT", ["Tomatoes", "Spinach"]),
    "fresh": ("Tshwane FreshMart", "SUPERMARKET", ["Tomatoes", "Potatoes", "Butternut"]),
    "coast": ("Coastal Produce Distributors", "DISTRIBUTOR", ["Cabbage", "Potatoes"]),
    "spaza": ("Soweto Spaza Wholesalers", "WHOLESALER", ["Potatoes", "Onions", "Eggs"]),
    "jam": ("Cape Jam Processors", "PROCESSOR", ["Strawberries"]),
}

# (farmer key, produce, category slug, quantity, unit, price, grade, available in N days)
LISTINGS = [
    ("thandi", "Tomatoes", "vegetables", "120", "KG", "14.00", "GRADE_A", 0),
    ("thandi", "Spinach", "vegetables", "60", "KG", "18.00", "PREMIUM", 0),
    ("sipho", "Tomatoes", "vegetables", "80", "KG", "12.50", "GRADE_B", 0),
    ("sipho", "Cabbage", "vegetables", "40", "UNIT", "9.00", "STANDARD", 0),
    ("lerato", "Tomatoes", "vegetables", "0.3", "TONNE", "15000.00", "ORGANIC", 2),
    ("lerato", "Butternut", "vegetables", "200", "KG", "8.50", "ORGANIC", 0),
    ("johan", "Potatoes", "vegetables", "500", "KG", "8.00", "GRADE_A", 0),
    ("mpho", "Tomatoes", "vegetables", "1", "TONNE", "9500.00", "STANDARD", 0),
    ("nomsa", "Cabbage", "vegetables", "300", "UNIT", "7.50", "GRADE_A", 0),
    ("nomsa", "Potatoes", "vegetables", "100", "BAG", "95.00", "STANDARD", 0),
    ("anele", "Strawberries", "fruits", "250", "KG", "45.00", "PREMIUM", 3),
    ("kagiso", "Eggs", "livestock-products", "200", "DOZEN", "32.00", "GRADE_A", 0),
]

# (buyer key, produce, quantity, unit, max price, needed in N days, max km, recurring)
REQUIREMENTS = [
    ("chef", "Tomatoes", "100", "KG", "15.00", 5, 50, "WEEKLY"),
    ("chef", "Potatoes", "50", "KG", None, 5, 50, "NONE"),
    ("fresh", "Butternut", "150", "KG", "10.00", 7, None, "NONE"),
    ("spaza", "Potatoes", "800", "KG", "9.00", 10, 60, "MONTHLY"),
    ("spaza", "Eggs", "100", "DOZEN", None, 4, 30, "WEEKLY"),
    ("coast", "Cabbage", "500", "UNIT", "8.00", 14, None, "NONE"),
    ("jam", "Strawberries", "300", "KG", "40.00", 10, None, "NONE"),
]


class Command(BaseCommand):
    help = "Create a realistic demo dataset (users, listings, orders, cooperative activity)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for every seeded user.")
        parser.add_argument("--force", action="store_true", help="Allow running when DEBUG is False.")

    @transaction.atomic
    def handle(self, *args, password, force, **options):
        if not settings.DEBUG and not force:
            raise CommandError("Refusing to seed demo data with DEBUG=False. Use --force if you are sure.")
        users = self._users(password)
        self._clear(users)
        self._profiles(users)
        listings = self._listings(users)
        self._requirements(users)
        self._orders(users, listings)
        self._coop(users)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(users)} users ({sum(u.role == Role.FARMER for u in users.values())} farmers). "
            f"Password for all: {password}"))

    # --- Users ------------------------------------------------------------------------------

    def _users(self, password):
        users = {}
        for key, (email, name, role, province, municipality, town, lat, lng, areas) in SEED_USERS.items():
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=password, role=role, display_name=name)
            else:
                user.display_name, user.role, user.is_active = name, role, True
                user.set_password(password)
                user.save()
            UserLocation.objects.update_or_create(user=user, defaults={
                "province": province, "municipality": municipality, "town": town,
                "latitude": Decimal(lat) if lat else None, "longitude": Decimal(lng) if lng else None,
                "preferred_delivery_areas": areas})
            users[key] = user
            self.stdout.write(f"  {role:<16} {email:<34} {town} ({'GPS' if lat else 'no GPS'})")
        return users

    def _clear(self, users):
        """Remove previous demo data owned by the seeded accounts so the run is repeatable."""
        from apps.ai.models import AIConversation
        from apps.bulk.models import BulkPurchase
        from apps.buyers.models import BuyerRequirement
        from apps.core.models import Notification
        from apps.equipment.models import EquipmentListing
        from apps.groups.models import FarmerGroup
        from apps.listings.models import ProduceListing
        from apps.messaging.models import Conversation
        from apps.orders.models import Order
        from apps.services.models import InsuranceProduct, SecurityAlert, SharedServiceRequest
        from apps.transport.models import TransportRequest

        ids = [u.pk for u in users.values()]
        Conversation.objects.filter(buyer_id__in=ids).delete()
        Order.objects.filter(buyer_id__in=ids).delete()
        BuyerRequirement.objects.filter(buyer_id__in=ids).delete()
        ProduceListing.objects.filter(farmer_id__in=ids).delete()
        BulkPurchase.objects.filter(organiser_id__in=ids).delete()
        TransportRequest.objects.filter(organiser_id__in=ids).delete()
        SharedServiceRequest.objects.filter(organiser_id__in=ids).delete()
        SecurityAlert.objects.filter(author_id__in=ids).delete()
        EquipmentListing.objects.filter(owner_id__in=ids).delete()
        FarmerGroup.objects.filter(created_by_id__in=ids).delete()
        Notification.objects.filter(user_id__in=ids).delete()
        AIConversation.objects.filter(user_id__in=ids).delete()
        InsuranceProduct.objects.filter(provider_name__startswith="[Demo]").delete()

    def _profiles(self, users):
        from apps.buyers.models import WholesaleBuyerProfile
        from apps.farmers.models import FarmerProfile

        for key, (farm, produce, size, verified) in FARM_PROFILES.items():
            FarmerProfile.objects.update_or_create(user=users[key], defaults={
                "farm_name": farm, "main_produce": produce, "farm_size_hectares": Decimal(size),
                "is_verified": verified, "bio": f"Family farm growing {', '.join(produce).lower()}."})
        for key, (name, btype, interests) in BUYER_PROFILES.items():
            WholesaleBuyerProfile.objects.update_or_create(user=users[key], defaults={
                "business_name": name, "business_type": btype, "produce_interests": interests})

    def _listings(self, users):
        from apps.listings.models import ProduceCategory, ProduceListing

        today = timezone.localdate()
        created = {}
        for key, produce, cat, qty, unit, price, grade, days in LISTINGS:
            created[(key, produce)] = ProduceListing.objects.create(
                farmer=users[key], produce_name=produce, category=ProduceCategory.objects.get(slug=cat),
                quantity_available=Decimal(qty), unit=unit, price_per_unit=Decimal(price), quality_grade=grade,
                available_from=today + timedelta(days=days), description=f"Fresh {produce.lower()} from the farm.")
        return created

    def _requirements(self, users):
        from apps.buyers.models import BuyerRequirement

        today = timezone.localdate()
        for key, produce, qty, unit, max_price, days, max_km, recurring in REQUIREMENTS:
            BuyerRequirement.objects.create(
                buyer=users[key], produce_name=produce, quantity_needed=Decimal(qty), unit=unit,
                max_price_per_unit=Decimal(max_price) if max_price else None, needed_by=today + timedelta(days=days),
                max_distance_km=max_km, recurring=recurring)

    def _orders(self, users, listings):
        from apps.messaging.services import send_message, start_conversation
        from apps.orders import services as orders

        def place(buyer, listing_key, qty):
            return orders.create_order(users[buyer], items=[{"listing_id": listings[listing_key].pk,
                                                             "quantity": Decimal(qty)}],
                                       delivery_date=timezone.localdate() + timedelta(days=3))

        # One order in each interesting state.
        place("chef", ("thandi", "Tomatoes"), "20")  # PENDING
        accepted = place("spaza", ("johan", "Potatoes"), "100")
        orders.transition(users["johan"], accepted.pk, "accept")
        dispatched = place("chef", ("thandi", "Spinach"), "10")
        orders.transition(users["thandi"], dispatched.pk, "accept")
        orders.transition(users["thandi"], dispatched.pk, "dispatch")
        done = place("fresh", ("lerato", "Butternut"), "50")
        for user, step in (("lerato", "accept"), ("lerato", "dispatch"), ("fresh", "confirm_receipt"),
                           ("fresh", "complete")):
            orders.transition(users[user], done.pk, step)
        orders.set_payment_status(users["lerato"], done.pk, "PAID")
        rejected = place("coast", ("nomsa", "Cabbage"), "30")
        orders.transition(users["nomsa"], rejected.pk, "reject", reason="Already promised to another buyer")

        conv = start_conversation(users["chef"], other_user_id=users["thandi"].pk,
                                  message="Hi Thandi, can you do 100 kg of tomatoes every week?")
        send_message(users["thandi"], conv.pk, "Yes, from next Monday. Delivery Tuesdays?")

    def _coop(self, users):
        from apps.bulk import services as bulk
        from apps.equipment.models import EquipmentListing
        from apps.groups import services as groups
        from apps.services import services as shared
        from apps.services.models import InsuranceProduct
        from apps.transport import services as transport

        today = timezone.localdate()
        group = groups.create_group(users["thandi"], name="Soweto & Joburg Growers", group_type="LOCATION",
                                    focus="vegetables", province=G, municipality="City of Johannesburg",
                                    town="Soweto", is_open=True,
                                    description="Vegetable growers sharing inputs, transport and market news.")
        for key in ("sipho", "kagiso"):
            groups.join(users[key], group.pk)
        groups.invite(users["thandi"], group.pk, users["johan"].pk)
        groups.create_post(users["thandi"], group.pk, "Fertiliser bulk buy closes Friday. Join in the Co-op hub!",
                           is_announcement=True)
        groups.create_group(users["mpho"], name="Limpopo Tomato Growers", group_type="PRODUCE", focus="tomatoes",
                            province=L, municipality="Polokwane Local Municipality", is_open=False)

        fertiliser = bulk.create_purchase(
            users["thandi"], group=None, item_name="LAN fertiliser (50 kg bags)", category="FERTILISER", unit="bag",
            unit_price=Decimal("450"), shared_fees=Decimal("350"), deadline=today + timedelta(days=7),
            supplier_name="Highveld Agri Supplies", organiser_quantity=Decimal("5"),
            discount_tiers=[{"min_total_quantity": "20", "unit_price": "420.00"},
                            {"min_total_quantity": "30", "unit_price": "400.00"}])
        bulk.join(users["sipho"], fertiliser.pk, 8)
        bulk.join(users["kagiso"], fertiliser.pk, 7)
        bulk.confirm(users["sipho"], fertiliser.pk)

        trip = transport.create_request(
            users["sipho"], pickup_province=G, pickup_municipality="City of Johannesburg", pickup_town="Soweto",
            destination="Joburg Fresh Produce Market", destination_town="Johannesburg",
            destination_municipality="City of Johannesburg", destination_province=G,
            destination_latitude=Decimal("-26.217500"), destination_longitude=Decimal("28.024400"),
            travel_date=today + timedelta(days=2), vehicle_description="4-tonne truck", total_cost=Decimal("1800"),
            cost_split_method="WEIGHT", capacity=Decimal("4000"), capacity_unit="KG",
            organiser_load={"load_weight_kg": Decimal("800")})
        transport.join(users["thandi"], trip.pk, load_weight_kg=Decimal("600"))

        EquipmentListing.objects.create(owner=users["johan"], type="TRACTOR", name="Massey Ferguson 375 with plough",
                                        rate=Decimal("850"), rate_unit="PER_DAY")
        EquipmentListing.objects.create(owner=users["lerato"], type="COLD_STORAGE", name="Pretoria cold room",
                                        rate=Decimal("15"), rate_unit="PER_TONNE_PER_DAY", capacity=Decimal("20"))
        EquipmentListing.objects.create(owner=users["thandi"], type="IRRIGATION", name="Drip irrigation kit (1 ha)",
                                        rate=Decimal("1200"), rate_unit="PER_MONTH")

        patrol = shared.create_service(users["thandi"], service_type="SECURITY", title="Soweto night patrol",
                                       description="Shared guard for farms near the Klipspruit.", province=G,
                                       municipality="City of Johannesburg", town="Soweto",
                                       total_monthly_cost=Decimal("4500"))
        shared.join(users["sipho"], patrol.pk)
        shared.create_alert(users["sipho"], alert_type="THEFT", title="Irrigation pipes stolen",
                            body="Pipes taken from two plots near the river on Tuesday night. Lock up equipment.",
                            province=G, municipality="City of Johannesburg", town="Soweto")

        for name, category, summary in (
            ("Crop hail and fire", "CROP", "Covers listed crops against hail and fire damage."),
            ("Livestock mortality", "LIVESTOCK", "Covers death of insured animals from listed causes."),
            ("Farm equipment", "EQUIPMENT", "Covers tractors and implements against theft and damage."),
        ):
            InsuranceProduct.objects.create(provider_name="[Demo] Example Agri Insurer", name=name, category=category,
                                            summary=summary, is_authorised_provider=False,
                                            website="https://example.com")
