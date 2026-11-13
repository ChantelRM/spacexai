import factory

from apps.accounts.factories import UserFactory

from .models import Province, UserLocation


class UserLocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserLocation

    user = factory.SubFactory(UserFactory)
    province = Province.GAUTENG
    municipality = "City of Johannesburg"
    town = "Johannesburg"
    latitude = None
    longitude = None
