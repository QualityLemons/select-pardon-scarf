from django.contrib import admin
from .models import Module, Milestone, EfficiencyThreshold, BonusCategory, SupervisorTip, GradeDescriptor, AssessmentResult, PrereqDismissal


class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 0
    fields = ('milestone_key', 'label', 'weight', 'sort_order')


class SupervisorTipInline(admin.TabularInline):
    model = SupervisorTip
    extra = 0
    fields = ('sort_order', 'icon', 'variant', 'tip_text')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'type', 'difficulty', 'sort_order')
    list_filter = ('type', 'difficulty')
    search_fields = ('id', 'title', 'description')
    inlines = [MilestoneInline, SupervisorTipInline]


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ('module', 'milestone_key', 'label', 'weight', 'sort_order')
    list_filter = ('module',)
    search_fields = ('label', 'milestone_key')


@admin.register(SupervisorTip)
class SupervisorTipAdmin(admin.ModelAdmin):
    list_display = ('module', 'sort_order', 'icon', 'variant')
    list_filter = ('module', 'variant')
    search_fields = ('tip_text',)


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_user_email', 'level_key', 'score', 'grade', 'tier_label', 'milestones_done', 'milestones_total', 'efficiency_label', 'bonus_earned', 'created_at')
    list_filter = ('level_key', 'grade', 'tier_label')
    search_fields = ('level_key', 'note', 'user__email', 'user__username')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user',)

    @admin.display(description='User', ordering='user__email')
    def get_user_email(self, obj):
        if obj.user:
            return obj.user.email or obj.user.username
        return '—'


@admin.register(GradeDescriptor)
class GradeDescriptorAdmin(admin.ModelAdmin):
    list_display = ('grade', 'label', 'min_score', 'description')


@admin.register(EfficiencyThreshold)
class EfficiencyThresholdAdmin(admin.ModelAdmin):
    list_display = ('module', 'exceptional', 'proficient', 'satisfactory', 'poor')


@admin.register(BonusCategory)
class BonusCategoryAdmin(admin.ModelAdmin):
    list_display = ('module', 'bonus_key', 'label', 'points')


@admin.register(PrereqDismissal)
class PrereqDismissalAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_user_email', 'level_key', 'dismissed_at')
    list_filter = ('level_key',)
    search_fields = ('user__email', 'user__username', 'level_key')
    readonly_fields = ('dismissed_at',)
    autocomplete_fields = ('user',)

    @admin.display(description='User', ordering='user__email')
    def get_user_email(self, obj):
        return obj.user.email or obj.user.username
