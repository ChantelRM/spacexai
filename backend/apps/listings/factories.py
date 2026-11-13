from datetime import date
from decimal import Decimal

import factory

from apps.accounts.factories import FarmerFactory

from .models import ProduceListing


class ProduceListingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProduceListing

    farmer = factory.SubFactory(FarmerFactory)
    produce_name = "Tomatoes"
    quantity_available = Decimal("100")
    unit = "KG"
    price_per_unit = Decimal("12.00")
    quality_grade = "GRADE_A"
    available_from = factory.LazyFunction(date.today)
