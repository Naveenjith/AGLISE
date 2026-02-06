from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden

def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("adminpanel:login")
        if request.user.role != "ADMIN":
            return HttpResponseForbidden("Admins only")
        return view_func(request, *args, **kwargs)
    return wrapper
