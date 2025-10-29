from django.shortcuts import render

# menus/views.py
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views import generic

from .models import Menu, MenuItem
from .forms import MenuForm, MenuItemForm

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        u = self.request.user
        return u.is_authenticated and (u.is_staff or u.is_superuser)

# ---------- Menus ----------
class MenuListView(StaffRequiredMixin, generic.ListView):
    model = Menu
    template_name = "menus/menu_list.html"
    context_object_name = "menus"

class MenuCreateView(StaffRequiredMixin, generic.CreateView):
    model = Menu
    form_class = MenuForm
    template_name = "menus/menu_form.html"

    def get_success_url(self):
        return reverse("menus:menu_detail", args=[self.object.pk])

class MenuDetailView(StaffRequiredMixin, generic.DetailView):
    model = Menu
    template_name = "menus/menu_detail.html"
    context_object_name = "menu"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Top-level items ordered
        ctx["top_items"] = self.object.items.filter(parent__isnull=True).order_by("order", "id")
        ctx["item_form"] = MenuItemForm(initial={"menu": self.object})
        return ctx

class MenuUpdateView(StaffRequiredMixin, generic.UpdateView):
    model = Menu
    form_class = MenuForm
    template_name = "menus/menu_form.html"

    def get_success_url(self):
        return reverse("menus:menu_detail", args=[self.object.pk])

class MenuDeleteView(StaffRequiredMixin, generic.DeleteView):
    model = Menu
    template_name = "menus/menu_delete.html"
    success_url = reverse_lazy("menus:menu_list")

# ---------- Menu Items ----------
class MenuItemCreateView(StaffRequiredMixin, generic.CreateView):
    model = MenuItem
    form_class = MenuItemForm
    template_name = "menus/menuitem_form.html"

    def get_menu(self):
        return get_object_or_404(Menu, pk=self.kwargs["menu_id"])

    def get_initial(self):
        init = super().get_initial()
        init["menu"] = self.get_menu()
        return init

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["menu"] = self.get_menu()   # <-- pass menu to the form
        return kwargs

    def form_valid(self, form):
        form.instance.menu = self.get_menu()  # force correct menu
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("menus:menu_detail", args=[self.object.menu_id])


class MenuItemUpdateView(StaffRequiredMixin, generic.UpdateView):
    model = MenuItem
    form_class = MenuItemForm
    template_name = "menus/menuitem_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Use the instance's menu to filter the Parent field
        kwargs["menu"] = self.object.menu
        return kwargs

    def get_success_url(self):
        return reverse("menus:menu_detail", args=[self.object.menu_id])


class MenuItemDeleteView(StaffRequiredMixin, generic.DeleteView):
    model = MenuItem
    template_name = "menus/menuitem_delete.html"

    def get_success_url(self):
        return reverse("menus:menu_detail", args=[self.object.menu_id])

