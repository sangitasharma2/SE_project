from django.contrib import admin
from django.urls import path, include
from core.views import HomePageView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", HomePageView.as_view(), name="home"),
    path("accounts/", include("accounts.urls")),
    path("transactions/", include("transactions.urls")),
]
urlpatterns += static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)