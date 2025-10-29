from django import forms
from django.forms import inlineformset_factory
from .models import Service, ServiceSection  # adjust import paths if different

# Tailwind-ish classes reused
_BASE_INPUT = "w-full rounded-2xl border border-white/40 bg-white/60 px-3 py-2.5"
_TEXTAREA   = _BASE_INPUT + " min-h-[10rem]"

def _first_existing(model_cls, candidates):
    names = {f.name for f in model_cls._meta.get_fields()}
    for c in candidates:
        if c in names:
            return c
    return None


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Detect likely title & image fields (works with many schemas)
        self.title_field_name = _first_existing(Service, ["main_title", "title", "name"])
        self.image_field_name = _first_existing(Service, ["image", "cover", "banner", "photo", "thumbnail"])

        for name, field in self.fields.items():
            if name == self.title_field_name:
                field.widget = forms.TextInput(attrs={"class": _BASE_INPUT, "placeholder": "Main Title"})
            elif name == self.image_field_name:
                field.widget = forms.ClearableFileInput(
                    attrs={"class": "block w-full cursor-pointer rounded-2xl border border-dashed "
                                    "border-emerald-300 bg-emerald-50/50 p-6 text-center"}
                )
            elif isinstance(field.widget, (forms.TextInput, forms.NumberInput)):
                field.widget.attrs.setdefault("class", _BASE_INPUT)
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", _TEXTAREA)


class ServiceSectionForm(forms.ModelForm):
    """
    Auto-detect common field names on ServiceSection:
      - title/heading/name/label/section_title
      - subtitle/sub_title/tagline/summary
      - description/body/content/text/details
      - order/position/sort/sort_order/index/sequence
    """
    class Meta:
        model = ServiceSection
        fields = "__all__"   # be flexible with schema

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Remember the actual field names so the template can address them
        self.section_title_name = _first_existing(
            ServiceSection, ["title", "heading", "name", "label", "section_title"]
        )
        self.subtitle_name = _first_existing(
            ServiceSection, ["subtitle", "sub_title", "tagline", "summary"]
        )
        self.description_name = _first_existing(
            ServiceSection, ["description", "body", "content", "text", "details"]
        )
        self.order_name = _first_existing(
            ServiceSection, ["order", "position", "sort", "sort_order", "index", "sequence"]
        )

        # Apply nice widgets where available
        if self.section_title_name and self.section_title_name in self.fields:
            self.fields[self.section_title_name].widget = forms.TextInput(
                attrs={"class": _BASE_INPUT, "placeholder": "Section"}
            )
        if self.subtitle_name and self.subtitle_name in self.fields:
            self.fields[self.subtitle_name].widget = forms.TextInput(
                attrs={"class": _BASE_INPUT, "placeholder": "sub title"}
            )
        if self.description_name and self.description_name in self.fields:
            self.fields[self.description_name].widget = forms.Textarea(
                attrs={"class": _TEXTAREA, "placeholder": "Description"}
            )
        if self.order_name and self.order_name in self.fields:
            self.fields[self.order_name].widget = forms.NumberInput(
                attrs={"class": _BASE_INPUT, "min": "0"}
            )


# The formset uses the flexible form above
ServiceSectionFormSet = inlineformset_factory(
    parent_model=Service,
    model=ServiceSection,
    form=ServiceSectionForm,
    fields="__all__",   # keep flexible
    extra=1,
    can_delete=True,
)

# Optional alias if your views import SectionFormSet
SectionFormSet = ServiceSectionFormSet
