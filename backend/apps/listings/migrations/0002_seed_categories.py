from django.db import migrations

CATEGORIES = [
    ("Vegetables", "vegetables"),
    ("Fruits", "fruits"),
    ("Grains", "grains"),
    ("Legumes", "legumes"),
    ("Livestock products", "livestock-products"),
    ("Dairy", "dairy"),
    ("Herbs", "herbs"),
    ("Other", "other"),
]


def seed(apps, schema_editor):
    ProduceCategory = apps.get_model("listings", "ProduceCategory")
    for name, slug in CATEGORIES:
        ProduceCategory.objects.update_or_create(slug=slug, defaults={"name": name})


def unseed(apps, schema_editor):
    apps.get_model("listings", "ProduceCategory").objects.filter(slug__in=[s for _, s in CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [("listings", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
