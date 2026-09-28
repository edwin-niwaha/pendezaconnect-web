from datetime import date
from io import BytesIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook
from openpyxl.utils.datetime import to_excel

from api.v1.serializers.client_serializers import ClientSerializer
from apps.client.forms import ClientForm
from apps.client.importing import import_clients
from apps.client.models import Client
from apps.client.profile_fields import PROFILE_FIELDS
from apps.users.models import Profile


class ClientProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="client-profile-manager")
        Profile.objects.create(user=self.user, role="manager")
        self.client.force_login(self.user)

    def workbook(self, headers, rows):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output

    def test_grouped_form_saves_new_fields_and_group_names(self):
        data = dict(
            full_name="Hope & Growth Group",
            reg_number="GROUP-2026-001",
            client_type="group",
            branch="Main",
            registration_date="2026-01-02",
            group_member_count="35",
            group_savings_cycle_months="12",
            group_chairperson="Test Chair",
            minimum_savings_amount="2000",
            mobile_telephone="0701234567",
            savings_frequency="monthly",
            next_of_kin_phone="0701234567",
        )
        response = self.client.post(reverse("register_client"), data)
        self.assertEqual(response.status_code, 302)
        client = Client.objects.get(reg_number=data["reg_number"])
        self.assertEqual(client.group_member_count, 35)
        self.assertEqual(client.branch, "Main")
        self.assertEqual(str(client.mobile_telephone), "+256701234567")
        data.update(occupation="Teacher", employment_sector="Formal", current_address="Kampala")
        self.assertEqual(self.client.post(reverse("update_client", args=[client.pk]), data).status_code, 302)
        client.refresh_from_db()
        self.assertEqual(client.occupation, "Teacher")
        self.assertEqual(client.group_savings_cycle_months, 12)

    def test_profile_export_directory_and_api(self):
        client = Client.objects.create(
            full_name="Example Client",
            reg_number="PROFILE-01",
            gender="Female",
            branch="Central",
            occupation="Teacher",
            group_member_count=0,
        )
        response = self.client.get(reverse("client_profile", args=[client.pk]))
        self.assertContains(response, "Teacher")
        self.assertContains(response, "Central")
        self.assertContains(response, "Next of kin")
        listing = self.client.get(reverse("client_list"), {"search": "Central"})
        self.assertContains(listing, "Example Client")
        self.assertContains(listing, reverse("client_profile", args=[client.pk]))
        export = self.client.get(reverse("client_list"), {"search": "Teacher", "export": "csv"})
        self.assertContains(export, "group_savings_cycle_months")
        self.assertContains(export, "PROFILE-01")
        data = ClientSerializer(client).data
        self.assertEqual(data["occupation"], "Teacher")
        self.assertEqual(data["group_member_count"], 0)
        self.assertTrue(set(PROFILE_FIELDS).issubset(data))

    def test_profile_requires_authorized_role(self):
        client = Client.objects.create(full_name="Example Client")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("client_profile", args=[client.pk])).status_code, 302)

    def test_validation_and_optional_legacy_fields(self):
        form = ClientForm({"full_name": "Example Client", "client_type": "individual"})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        for invalid in (
            {"date_of_birth": "2999-01-01"},
            {"minimum_savings_amount": "-1"},
            {"group_savings_cycle_months": "0"},
            {"date_of_birth": "2000-01-01", "registration_date": "1999-01-01"},
        ):
            form = ClientForm({"full_name": "Example Client", "client_type": "individual", **invalid})
            self.assertFalse(form.is_valid())
        with self.assertRaises(ValidationError):
            Client(full_name="Example Client", date_of_birth=date(2999, 1, 1)).full_clean()

    def test_legacy_import_maps_headers_dates_gender_sector_and_kin(self):
        source = self.workbook(
            [
                "reg_number",
                "full_name",
                "Gender",
                "BirthDate",
                "RegDate",
                "Profession",
                "Occupation",
                "NextOfKin",
                "Savings_Freq",
                "Min_Savings",
                "Grp_saving_cycle_length",
                "Branch",
            ],
            [
                [
                    "IMPORT-1",
                    "Imported Client",
                    "F",
                    to_excel(date(1990, 1, 1)),
                    to_excel(date(2020, 1, 1)),
                    "Teacher",
                    "Formal",
                    "Test Kin-0701234567",
                    "Monthly",
                    "2,000",
                    "1 year",
                    "Main",
                ]
            ],
        )
        self.assertEqual(import_clients(source), [])
        client = Client.objects.get(reg_number="IMPORT-1")
        self.assertEqual(client.gender, "Female")
        self.assertEqual(client.date_of_birth, date(1990, 1, 1))
        self.assertEqual(client.registration_date, date(2020, 1, 1))
        self.assertEqual(client.occupation, "Teacher")
        self.assertEqual(client.employment_sector, "Formal")
        self.assertEqual(client.next_of_kin_name, "Test Kin")
        self.assertEqual(str(client.next_of_kin_phone), "+256701234567")
        self.assertEqual(client.group_savings_cycle_months, 12)

    def test_import_valid_rows_survive_invalid_and_existing_records_are_preserved(self):
        client = Client.objects.create(reg_number="EXIST-1", full_name="Original Client")
        source = self.workbook(
            ["reg_number", "full_name", "email"],
            [
                ["BAD-1", "Invalid Client", "0701234567"],
                ["EXIST-1", "Replacement Client", ""],
                ["GOOD-1", "Valid Client", ""],
            ],
        )
        errors = import_clients(source)
        self.assertEqual(len(errors), 1)
        client.refresh_from_db()
        self.assertEqual(client.full_name, "Replacement Client")
        self.assertFalse(Client.objects.filter(reg_number="BAD-1").exists())
        self.assertTrue(Client.objects.filter(reg_number="GOOD-1").exists())

    def test_ambiguous_work_and_savings_cycle_are_reported(self):
        source = self.workbook(
            ["reg_number", "full_name", "Profession", "Type_of_work"], [["AMB-1", "Test Client", "Teacher", "Farmer"]]
        )
        self.assertIn("Conflicting occupation", import_clients(source)[0])
        source = self.workbook(["reg_number", "full_name", "Grp_saving_cycle_length"], [["AMB-2", "Test Client", 1]])
        self.assertIn("explicit unit", import_clients(source)[0])
        self.assertEqual(Client.objects.count(), 0)

    def test_photo_cleaner_preserves_existing_cloudinary_reference(self):
        from cloudinary import CloudinaryResource

        form = ClientForm()
        photo = CloudinaryResource("client_uploads/existing")
        form.cleaned_data = {"picture": photo}
        self.assertIs(form.clean_picture(), photo)

    def test_directory_preview_contains_profile_fields_without_sidebar(self):
        record = Client.objects.create(
            full_name="Preview Client",
            reg_number="PREVIEW-1",
            next_of_kin_name="Example Kin",
            occupation="Teacher",
            savings_goal="School fees",
        )
        response = self.client.get(reverse("client_list"))
        self.assertContains(response, f'data-client-preview="preview-{record.pk}"')
        self.assertContains(response, "Example Kin")
        self.assertContains(response, "School fees")
        self.assertContains(response, 'id="client-preview"', count=1)
        self.assertNotContains(response, 'id="sidebar"')
        profile = self.client.get(reverse("client_profile", args=[record.pk]))
        self.assertNotContains(profile, 'id="sidebar"')
        self.assertContains(profile, "Next of kin")

    def test_update_page_preserves_invalid_values_and_has_full_width_layout(self):
        record = Client.objects.create(full_name="Update Client", reg_number="EDIT-1")
        response = self.client.get(reverse("update_client", args=[record.pk]))
        self.assertContains(response, "Save changes")
        self.assertContains(response, 'class="form-section-nav"')
        self.assertNotContains(response, 'id="sidebar"')
        response = self.client.post(
            reverse("update_client", args=[record.pk]),
            {
                "full_name": "Update Client",
                "client_type": "individual",
                "branch": "Central",
                "minimum_savings_amount": "-5",
                "next_of_kin_name": "Example Kin",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please correct the highlighted fields.")
        self.assertContains(response, 'value="Central"')
        self.assertContains(response, 'value="Example Kin"')
        record.refresh_from_db()
        self.assertEqual(record.branch, "")

    def test_import_matches_reg_preserves_blanks_zero_and_client_id(self):
        record = Client.objects.create(
            reg_number="  Reg-22  ", full_name="Original", email="test@example.com", minimum_savings_amount=500
        )
        source = self.workbook(
            ["reg_number", "full_name", "email", "minimum_savings_amount"],
            [["reg-22", "", "", 0], ["NEW-22", "New Client", "", 10]],
        )
        result = import_clients(source, report=True)
        self.assertEqual((result.created, result.updated, result.errors), (1, 1, []))
        record.refresh_from_db()
        self.assertEqual(record.full_name, "Original")
        self.assertEqual(record.email, "test@example.com")
        self.assertEqual(record.minimum_savings_amount, 0)
        self.assertEqual(Client.objects.count(), 2)

    def test_import_duplicate_keys_and_invalid_updates_leave_records_unchanged(self):
        record = Client.objects.create(reg_number="DUP", full_name="Original")
        source = self.workbook(["reg_number", "full_name"], [["DUP", "First"], [" dup ", "Second"]])
        self.assertEqual(len(import_clients(source)), 2)
        source = self.workbook(["reg_number", "full_name", "email"], [["DUP", "Changed", "invalid-email"]])
        self.assertEqual(len(import_clients(source)), 1)
        record.refresh_from_db()
        self.assertEqual(record.full_name, "Original")
        Client.objects.create(reg_number=" dup ", full_name="Duplicate")
        source = self.workbook(["reg_number", "full_name"], [["DUP", "Ambiguous"]])
        self.assertIn("Multiple existing clients", import_clients(source)[0])

    def test_prepared_updates_sheet_and_joint_account_codes(self):
        workbook = Workbook()
        workbook.active.title = "Instructions"
        sheet = workbook.create_sheet("Updates")
        sheet.append(["reg_number", "full_name", "gender"])
        for code in ("G", "C", "J", "JT", "M/F", "M", "F"):
            sheet.append([code, "Example " + code, code])
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        result = import_clients(output, report=True)
        self.assertEqual((result.created, result.errors), (7, []))
        self.assertEqual(Client.objects.get(reg_number="M/F").client_type, "joint")
        self.assertEqual(Client.objects.get(reg_number="G").gender, "")
        self.assertEqual(Client.objects.get(reg_number="F").gender, "Female")

    def test_import_upload_displays_created_and_updated_counts(self):
        self.user.profile.role = "administrator"
        self.user.profile.staff_role = "administrator"
        self.user.profile.save()
        Client.objects.create(reg_number="OLD", full_name="Old Client")
        source = self.workbook(["reg_number", "full_name"], [["OLD", "Updated Client"], ["NEW", "New Client"]])
        source.name = "clients.xlsx"
        response = self.client.post(reverse("import_client_data"), {"excel_file": source})
        self.assertContains(response, "Import results")
        self.assertEqual(response.context["result"].created, 1)
        self.assertEqual(response.context["result"].updated, 1)
