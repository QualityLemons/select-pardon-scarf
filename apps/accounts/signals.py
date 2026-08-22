from django.conf import settings
from django.core.mail import mail_admins
from django.dispatch import receiver
from axes.signals import user_locked_out
import datetime


@receiver(user_locked_out)
def notify_admins_on_lockout(sender, request, username, ip_address, **kwargs):
    if not getattr(settings, 'ADMINS', None):
        return

    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

    subject = f'Account locked out: {username}'
    message = (
        f'An account has been locked after too many failed login attempts.\n\n'
        f'Username : {username}\n'
        f'IP Address: {ip_address}\n'
        f'Time      : {timestamp}\n\n'
        f'To unlock the account, visit the admin panel:\n'
        f'/admin/axes/accessattempt/\n'
    )

    mail_admins(subject, message, fail_silently=True)
