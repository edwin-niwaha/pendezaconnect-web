from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class ApiDocumentationTests(TestCase):
    def test_documentation_pages_are_public(self):
        for name in ("api-docs-home", "api-docs-swagger", "api-docs-redoc"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_schema_is_json_and_scoped_to_api(self):
        response = self.client.get(reverse("api-docs-schema"), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["info"]["title"], "Pendeza Connect API")
        self.assertEqual(schema["info"]["version"], "v1")
        self.assertIn("Bearer", schema["securityDefinitions"])
        self.assertTrue(schema["paths"])
        self.assertTrue(all(not path.startswith("/admin/") for path in schema["paths"]))

    def test_home_links_views_and_shows_bearer_example(self):
        response = self.client.get(reverse("api-docs-home"))
        self.assertContains(response, reverse("api-docs-swagger"))
        self.assertContains(response, reverse("api-docs-redoc"))
        self.assertContains(response, reverse("api-docs-schema"))
        self.assertContains(response, "Authorization: Bearer")
