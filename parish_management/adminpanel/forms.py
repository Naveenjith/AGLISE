from django import forms
from registry.models import Church, Package
from django.core.exceptions import ValidationError

class PackageForm(forms.ModelForm):
    class Meta:
        model = Package
        fields = "__all__"
        widgets = {
            "is_custom": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_trial": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned_data = super().clean()

        is_trial = cleaned_data.get("is_trial")
        is_custom = cleaned_data.get("is_custom")

        trial_member_limit = cleaned_data.get("trial_member_limit")

        rate_monthly = cleaned_data.get("rate_per_member_monthly")
        rate_yearly = cleaned_data.get("rate_per_member_yearly")
        upgrade_monthly = cleaned_data.get("upgrade_rate_monthly")
        upgrade_yearly = cleaned_data.get("upgrade_rate_yearly")

        # -------------------------
        # TRIAL VALIDATION
        # -------------------------
        if is_trial:
            if not trial_member_limit:
                raise ValidationError(
                    "Trial package must have a trial member limit (e.g. 5)."
                )

            if any([rate_monthly, rate_yearly, upgrade_monthly, upgrade_yearly]):
                raise forms.ValidationError(
                    "Trial package must not have pricing or upgrade rates."
                )
        # -------------------------
        # INVALID COMBINATION
        # -------------------------
        if is_trial and is_custom:
            raise forms.ValidationError(
                "Package cannot be both Trial and Custom."
            )

        return cleaned_data
        
        

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if field.widget.input_type == "checkbox":
                continue
            field.widget.attrs["class"] = "form-control"

    


# forms.py
class ChurchForm(forms.ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = Church
        fields = [
            "name",
            "address",
            "city",
            "vicar",
            "asst_vicar1",
            "asst_vicar2",
            "asst_vicar3",
            "diocese_name",
            "logo",
            "email",
            "phone_number",
        ]
        widgets = {
            "address": forms.Textarea(attrs={
                "rows": 3,              # ✅ smaller height
                "placeholder": "Church address",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"

        # Explicit UX hint
        self.fields["email"].widget.attrs.update({
            "placeholder": "official church email",
            "required": "required",
        })



class ChurchSubscriptionForm(forms.Form):
    package = forms.ModelChoiceField(
        queryset=Package.objects.all(),
        required=False,
        empty_label="--------- Select Package ---------"
    )

    billing_cycle = forms.ChoiceField(
        choices=(
            ("", "--------- Select Billing Cycle ---------"),
            ("MONTHLY", "Monthly"),
            ("YEARLY", "Yearly"),
        ),
        required=False,
    )

    custom_capacity = forms.IntegerField(
        required=False,
        min_value=10,
        label="Custom Member Capacity"
    )

    def clean(self):
        cleaned_data = super().clean()

        package = cleaned_data.get("package")
        billing_cycle = cleaned_data.get("billing_cycle")
        custom_capacity = cleaned_data.get("custom_capacity")

        # Normalize empty billing cycle
        if billing_cycle == "":
            billing_cycle = None
            cleaned_data["billing_cycle"] = None

        # -------------------------
        # NO PACKAGE SELECTED
        # -------------------------
        if not package:
            if billing_cycle or custom_capacity:
                raise forms.ValidationError(
                    "Please select a package before choosing billing options."
                )
            return cleaned_data

        # -------------------------
        # TRIAL PACKAGE RULES
        # -------------------------
        if package.is_trial:
            if billing_cycle or custom_capacity:
                raise forms.ValidationError(
                    "Trial package does not require billing cycle or capacity."
                )
            return cleaned_data

        # -------------------------
        # PAID PACKAGE RULES
        # -------------------------
        if not billing_cycle:
            raise forms.ValidationError(
                "Billing cycle is required for paid packages."
            )

        # -------------------------
        # CUSTOM PACKAGE RULES
        # -------------------------
        if package.is_custom:
            if not custom_capacity:
                raise forms.ValidationError(
                    "Custom member capacity is required for custom package."
                )
        else:
            if custom_capacity:
                raise forms.ValidationError(
                    "Custom capacity is allowed only for custom packages."
                )

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
