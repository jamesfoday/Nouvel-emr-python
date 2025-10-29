from django import forms
from .models import Menu, MenuItem

# Reusable Tailwind classes
INPUT_CLS = (
    "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 "
    "text-slate-900 placeholder-slate-400 "
    "focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
)
SELECT_CLS = (
    "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 "
    "text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
)
TEXTAREA_CLS = (
    "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 "
    "text-slate-900 placeholder-slate-400 min-h-[7rem] "
    "focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
)
CHECK_CLS = "h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
NUMBER_CLS = INPUT_CLS

class MenuForm(forms.ModelForm):
    class Meta:
        model = Menu
        fields = ["key", "name", "description", "is_active"]
        widgets = {
            "key": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "e.g. main"}),
            "name": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "Menu display name"}),
            "description": forms.Textarea(attrs={"class": TEXTAREA_CLS, "rows": 4, "placeholder": "Optional description…"}),
            "is_active": forms.CheckboxInput(attrs={"class": CHECK_CLS}),
        }

class MenuItemForm(forms.ModelForm):
    url_kwargs = forms.JSONField(required=False, widget=forms.Textarea(
        attrs={"class": TEXTAREA_CLS, "placeholder": '{"slug": "service-slug"}'}
    ))
    url_query = forms.JSONField(required=False, widget=forms.Textarea(
        attrs={"class": TEXTAREA_CLS, "placeholder": '{"ref": "campaign"}'}
    ))

    class Meta:
        model = MenuItem
        fields = [
            "menu", "parent", "label", "icon", "order", "is_active", "visibility",
            "url_kind", "named_url", "url_kwargs", "url_query",
            "internal_path", "external_url", "open_in_new_tab",
            "is_mega", "mega_columns",
        ]
        widgets = {
            "menu": forms.Select(attrs={"class": SELECT_CLS}),
            "parent": forms.Select(attrs={"class": SELECT_CLS}),
            "label": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "Label shown to users"}),
            "icon": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "Optional icon class/name"}),
            "order": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 0}),
            "is_active": forms.CheckboxInput(attrs={"class": CHECK_CLS}),
            "visibility": forms.Select(attrs={"class": SELECT_CLS}),
            "url_kind": forms.Select(attrs={"class": SELECT_CLS}),
            "named_url": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "e.g. services:list"}),
            "internal_path": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "/pricing/"}),
            "external_url": forms.URLInput(attrs={"class": INPUT_CLS, "placeholder": "https://example.com"}),
            "open_in_new_tab": forms.CheckboxInput(attrs={"class": CHECK_CLS}),
            "is_mega": forms.CheckboxInput(attrs={"class": CHECK_CLS}),
            "mega_columns": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 2, "max": 6}),
        }

    def __init__(self, *args, **kwargs):
        # pass `menu` in from the view
        menu: Menu | None = kwargs.pop("menu", None)
        super().__init__(*args, **kwargs)

        # Friendly empty label to indicate "top level"
        self.fields["parent"].empty_label = "— Top level (no parent) —"

        # Default to no options until a menu is known
        qs = MenuItem.objects.none()

        # Determine the menu to filter by: passed in or from instance.initial
        if menu is None:
            # when editing, instance already has a menu
            menu = getattr(self.instance, "menu", None)

        if menu:
            # Only allow parents from SAME menu and only top-level items
            qs = MenuItem.objects.filter(menu=menu, parent__isnull=True).order_by("order", "label")

            # When editing, don't allow selecting self as parent
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

        self.fields["parent"].queryset = qs