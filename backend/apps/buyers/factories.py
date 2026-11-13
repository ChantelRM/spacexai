from datetime import date, timedelta
from decimal import Decimal

import factory

from apps.accounts.factories import BuyerFactory

from .models import BuyerRequirement


class BuyerRequirementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BuyerRequirement

    buyer = factory.SubFactory(BuyerFactory)
    produce_name = "Tomatoes"
    quantity_needed = Decimal("100")
    unit = "KG"
    needed_by = factory.LazyFunction(lambda: date.today() + timedelta(days=5))
