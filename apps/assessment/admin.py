from django.contrib import admin

from .models import AssessmentResult


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "level_key", "score", "grade", "created_at")
    list_filter = ("level_key", "grade")
    search_fields = ("user__username", "level_key", "note")
    readonly_fields = ("created_at",)
