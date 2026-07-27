from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import path, reverse
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined', 'change_password_link')
    list_filter = ('is_staff', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'is_staff', 'is_active'),
        }),
    )

    readonly_fields = ('date_joined',)

    def get_urls(self):
        app = self.model._meta.app_label
        model = self.model._meta.model_name
        extra = [
            path(
                '<id>/password/',
                self.admin_site.admin_view(self.user_change_password),
                name=f'{app}_{model}_password_change',
            ),
        ]
        return extra + super().get_urls()

    @admin.display(description='Password')
    def change_password_link(self, obj):
        app = self.model._meta.app_label
        model = self.model._meta.model_name
        url = reverse(f'admin:{app}_{model}_password_change', args=[obj.pk])
        return format_html('<a href="{}">Change password</a>', url)
