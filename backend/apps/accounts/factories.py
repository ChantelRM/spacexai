"""factory_boy factories. Other apps may import these in their own tests."""
import factory

from .models import Role, User

DEFAULT_TEST_PASSWORD = "Str0ng-Test-Passw0rd!"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    display_name = factory.Sequence(lambda n: f"User {n}")
    role = Role.FARMER
    phone_number = factory.Sequence(lambda n: f"+2782000{n:04d}")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or DEFAULT_TEST_PASSWORD)
        if create:
            obj.save(update_fields=["password"])


class FarmerFactory(UserFactory):
    role = Role.FARMER
    display_name = factory.Sequence(lambda n: f"Farmer {n}")


class BuyerFactory(UserFactory):
    role = Role.WHOLESALE_BUYER
    display_name = factory.Sequence(lambda n: f"Buyer {n}")
