from django.contrib import admin

from .models import TransportParticipant, TransportRequest


class ParticipantInline(admin.TabularInline):
    model = TransportParticipant
    extra = 0
    raw_id_fields = ["farmer"]


@admin.register(TransportRequest)
class TransportRequestAdmin(admin.ModelAdmin):
    list_display = ["destination", "pickup_town", "travel_date", "organiser", "cost_split_method", "status"]
    list_filter = ["status", "cost_split_method", "pickup_province"]
    raw_id_fields = ["organiser"]
    inlines = [ParticipantInline]
