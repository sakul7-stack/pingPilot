from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from heartbeat.models import Monitor
from .models import StatusPage, StatusPageMonitor


class StatusPageForm(forms.ModelForm):
    class Meta:
        model = StatusPage
        exclude = ['user', 'slug', 'domain_verified',
                    'domain_verification_token', 'view_count',
                    'created_at', 'updated_at', 'domain_claimed_at',
                    'dns_instructions']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off', 'placeholder': 'e.g. My Company Status'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'autocomplete': 'off', 'rows': 3}),
            'logo_url': forms.URLInput(attrs={'class': 'form-control', 'autocomplete': 'off', 'placeholder': 'https://example.com/logo.png'}),
            'favicon_url': forms.URLInput(attrs={'class': 'form-control', 'autocomplete': 'off', 'placeholder': 'https://example.com/favicon.ico'}),
            'theme': forms.Select(attrs={'class': 'form-select'}),
            'layout': forms.Select(attrs={'class': 'form-select'}),
            'sort_order': forms.Select(attrs={'class': 'form-select'}),
            'show_uptime': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_response_time': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_incidents': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_timeline': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_graph': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'header_color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'accent_color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'custom_domain': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off', 'placeholder': 'status.yourdomain.com'}),
            'meta_description': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'footer_text': forms.Textarea(attrs={'class': 'form-control', 'autocomplete': 'off', 'rows': 2}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'password_protected': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'access_password': forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
        }


class StatusPageCreateForm(StatusPageForm):
    class Meta(StatusPageForm.Meta):
        fields = ['title', 'description', 'theme']


class StatusPageMonitorForm(forms.ModelForm):
    monitor = forms.ModelChoiceField(
        queryset=Monitor.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = StatusPageMonitor
        fields = ['monitor', 'display_name', 'show_on_page']
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'show_on_page': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        status_page = kwargs.pop('status_page', None)
        super().__init__(*args, **kwargs)
        if user:
            monitors = user.monitor_set.all().order_by('group', 'name')
            self.fields['monitor'].queryset = monitors
            self.fields['monitor'].choices = [
                (mon.pk, self._monitor_label(mon)) for mon in monitors
            ]

    @staticmethod
    def _monitor_label(mon):
        if mon.group:
            return f"[{mon.group}] {mon.name}"
        return mon.name


class BaseStatusPageMonitorFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['user'] = self.user
        if hasattr(self, 'instance'):
            kwargs['status_page'] = self.instance
        return super()._construct_form(i, **kwargs)


StatusPageMonitorFormSet = inlineformset_factory(
    StatusPage, StatusPageMonitor,
    form=StatusPageMonitorForm,
    formset=BaseStatusPageMonitorFormSet,
    extra=0,
    can_delete=True,
)
