from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html
from django.urls import path, reverse
from .models import CustomUser


# ---------------------------------------------------------------------------
# Password-change audit log – proxy model + admin
# ---------------------------------------------------------------------------

class PasswordChangeLogEntry(LogEntry):
    """Proxy of LogEntry used solely for the password-change audit view."""

    class Meta:
        proxy = True
        verbose_name = 'Password change log'
        verbose_name_plural = 'Password change log'


@admin.register(PasswordChangeLogEntry)
class PasswordChangeLogAdmin(admin.ModelAdmin):
    """Read-only admin page showing only password-change audit entries."""

    list_display = ('action_time', 'acting_admin', 'affected_user', 'change_message')
    list_filter = ()
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'object_repr')
    ordering = ('-action_time',)
    date_hierarchy = 'action_time'

    # Never allow any writes through this view.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        """Show only entries written by the password-change audit hook."""
        qs = super().get_queryset(request)
        return qs.filter(
            action_flag=CHANGE,
            change_message='Password changed by admin.',
        ).select_related('user', 'content_type')

    # ---- custom display columns ----------------------------------------

    @admin.display(description='Admin who acted', ordering='user__email')
    def acting_admin(self, obj):
        """The staff member who triggered the password change."""
        return obj.user.get_full_name() or obj.user.email

    @admin.display(description='Affected user', ordering='object_repr')
    def affected_user(self, obj):
        """The user whose password was changed (stored in object_repr)."""
        return obj.object_repr


# ---------------------------------------------------------------------------
# CustomUser admin
# ---------------------------------------------------------------------------

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = (
        'email', 'first_name', 'last_name',
        'is_staff', 'is_active', 'date_joined',
        'change_password_link', 'audit_log_link',
    )
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

    @admin.display(description='Audit log')
    def audit_log_link(self, obj):
        """Link to the filtered password-change audit log."""
        url = reverse('admin:accounts_passwordchangelogentry_changelist')
        return format_html(
            '<a href="{}?q={}">View log</a>',
            url,
            obj.email,
        )

    # ------------------------------------------------------------------ #
    # Self-password-change safety note                                     #
    # ------------------------------------------------------------------ #
    # An admin who navigates to their own entry and uses this form will NOT
    # be locked out of the admin.  Django's built-in user_change_password()
    # view (inherited from UserAdmin) calls update_session_auth_hash() after
    # a successful save, which re-signs the current session with the new
    # password hash so the admin stays logged in without interruption.
    #
    # This behaviour is intentional: the admin is authenticated for the full
    # duration of their browser session regardless of whether they changed
    # their own password or another user's password.
    # ------------------------------------------------------------------ #

    def has_change_permission(self, request, obj=None):
        """
        Block non-superuser staff from editing a superuser account.

        A staff user who holds the generic 'change_customuser' permission can
        access the admin change form for ordinary users, but must NOT be able
        to alter a superuser's record (including changing their password).
        Allowing that would let a lower-privilege account hijack a superuser's
        credentials, which is a classic privilege-escalation vector.
        """
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def user_change_password(self, request, id, form_url=''):
        """Override to log an audit entry whenever a password change is saved."""
        # Capture the target user's pk before delegating to the parent view.
        # The parent view handles GET (render form) and POST (save + redirect).
        # We detect a successful POST by comparing the response status code:
        # a redirect (302) means the form was submitted and validated correctly.
        response = super().user_change_password(request, id, form_url=form_url)

        if request.method == 'POST' and hasattr(response, 'status_code') and response.status_code == 302:
            try:
                target_user = self.get_object(request, id)
                if target_user is not None:
                    ct = ContentType.objects.get_for_model(target_user)
                    LogEntry.objects.log_action(
                        user_id=request.user.pk,
                        content_type_id=ct.pk,
                        object_id=target_user.pk,
                        object_repr=str(target_user),
                        action_flag=CHANGE,
                        change_message='Password changed by admin.',
                    )
            except Exception:
                # Never let audit logging break the actual password-change flow.
                pass

        return response
