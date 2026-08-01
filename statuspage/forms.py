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
                    'created_at', 'updated_at']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'header_color': forms.TextInput(attrs={'type': 'color'}),
            'accent_color': forms.TextInput(attrs={'type': 'color'}),
            'access_password': forms.PasswordInput(),
            'footer_text': forms.Textarea(attrs={'rows': 2}),
        }


class StatusPageMonitorForm(forms.ModelForm):
    monitor = forms.ModelChoiceField(
        queryset=Monitor.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = StatusPageMonitor
        fields = ['monitor', 'display_name', 'show_on_page']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        status_page = kwargs.pop('status_page', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['monitor'].queryset = user.monitor_set.all()


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
    extra=5,
    can_delete=True,
)
