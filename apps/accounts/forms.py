from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class EditProfileForm(forms.Form):
    first_name = forms.CharField(
        label='First Name',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'given-name'}),
    )
    last_name = forms.CharField(
        label='Last Name',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'family-name'}),
    )
    email = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        qs = User.objects.filter(email=email)
        if self._user:
            qs = qs.exclude(pk=self._user.pk)
        if qs.exists():
            raise forms.ValidationError('That email address is already in use.')
        return email

    def save(self):
        if not self._user:
            return
        self._user.first_name = self.cleaned_data['first_name']
        self._user.last_name  = self.cleaned_data['last_name']
        self._user.email      = self.cleaned_data['email']
        self._user.save(update_fields=['first_name', 'last_name', 'email'])


class RegistrationForm(forms.Form):
    email = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={'autocomplete': 'email', 'autofocus': True}),
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def clean_email(self):
        # Intentionally do not check for an existing account here. Doing so
        # (and surfacing a distinct error) lets an unauthenticated caller
        # enumerate registered accounts, which combined with per-username
        # login lockouts enables a targeted denial-of-service. The
        # duplicate-email case is instead handled uniformly in save() so the
        # form response looks the same whether or not the address is taken.
        return self.cleaned_data['email'].lower()

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned

    def save(self):
        """
        Create the account, or silently no-op if the email is already
        registered. Returns the new user, or None when no account was
        created (either because the email was already taken). Callers must
        give the same outward response in both cases to avoid disclosing
        account existence.
        """
        email = self.cleaned_data['email']
        password = self.cleaned_data['password1']
        if User.objects.filter(email=email).exists():
            return None
        return User.objects.create_user(email=email, password=password)
