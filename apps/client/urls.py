from django.urls import path

from . import views

urlpatterns = [
    path("add/draft/", views.save_registration_draft, name="save_registration_draft"),
    path("profile/<int:pk>/", views.client_profile, name="client_profile"),
    path("add/", views.register_client, name="register_client"),
    path("photo/", views.upload_client_photo, name="upload_client_photo"),
    path("list/", views.client_list, name="client_list"),
    path("inactive/", views.client_list, {"inactive_report": True}, name="inactive_clients_report"),
    path("<int:pk>/status/", views.change_client_status, name="change_client_status"),
    path(
        "photo/<int:pk>/delete/",
        views.delete_client_profile_picture,
        name="delete_client_profile_picture",
    ),
    path("update/<int:pk>", views.update_client, name="update_client"),
    path("delete/<int:pk>", views.delete_client, name="delete_client"),
    path("import/", views.import_client_data, name="import_client_data"),
    path("import/<int:pk>/", views.client_import_status, name="client_import_status"),
    path("delete-confirm/", views.delete_confirm, name="delete_confirm"),
    path(
        "seven-hills-registration/",
        views.seven_hills_registration_view,
        name="seven_hills_registration",
    ),
    path("seven-hills", views.seven_hills_list, name="seven_hills_list"),
    path(
        "seven-hills/update/<int:pk>",
        views.update_seven_hills,
        name="update_seven_hills",
    ),
    path(
        "seven-hills/delete/<int:pk>",
        views.delete_seven_hills,
        name="delete_seven_hills",
    ),
    path(
        "seven-hills/details/<int:pk>",
        views.seven_hills_details,
        name="seven_hills_details",
    ),
]
