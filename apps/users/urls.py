from django.urls import path

from .views import (
    RegisterView,
    contact_us,
    delete_doc,
    delete_ebook,
    delete_feedback,
    delete_policy,
    delete_profile,
    doc_list,
    ebook_list,
    home,
    open_policy_document,
    policy_list,
    policy_report,
    profile,
    profile_list,
    read_policy,
    update_doc,
    update_ebook,
    update_policy,
    update_profile,
    upload_doc,
    upload_ebook,
    upload_policy,
    user_feedback,
    validate_policy,
    validate_user_feedback,
)

urlpatterns = [
    path("", home, name="users-home"),
    path("register/", RegisterView.as_view(), name="users-register"),
    # Profile
    path("profile/", profile, name="users-profile"),
    path("profile-list/", profile_list, name="profile_list"),
    path("profile/update/<int:pk>", update_profile, name="update_profile"),
    path("profile/delete/<int:pk>", delete_profile, name="delete_profile"),
    # Polcies
    path("policy-list/", policy_list, name="policy_list"),
    path("create-policy/", upload_policy, name="upload_policy"),
    path("policy/update/<int:pk>", update_policy, name="update_policy"),
    path("policy/delete/<int:pk>", delete_policy, name="delete_policy"),
    path("policy/document/<int:pk>/", open_policy_document, name="open_policy_document"),
    path("policy/validate/<int:policy_id>/", validate_policy, name="validate_policy"),
    path("policy/read/<int:policy_id>/", read_policy, name="read_policy"),
    path("policy/read/", policy_report, name="policy_report"),
    # Ebook
    path("ebook/upload/", upload_ebook, name="upload_ebook"),
    path("ebook/list/", ebook_list, name="ebook_list"),
    path("ebook/delete/<int:pk>", delete_ebook, name="delete_ebook"),
    path("ebook/update/<int:pk>", update_ebook, name="update_ebook"),
    # User Feedback
    path("contact-us/", contact_us, name="contact_us"),
    path("feedback/", user_feedback, name="user_feedback"),
    path("feedback/delete/<int:pk>", delete_feedback, name="delete_feedback"),
    path(
        "feedback/validate/<int:contact_id>/",
        validate_user_feedback,
        name="validate_user_feedback",
    ),
    # Documentats
    path("document/upload/", upload_doc, name="upload_doc"),
    path("document/list/", doc_list, name="doc_list"),
    path("document/delete/<int:pk>", delete_doc, name="delete_doc"),
    path("document/update/<int:pk>", update_doc, name="update_doc"),
]
