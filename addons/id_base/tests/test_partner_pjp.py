# Part of odooca-fmcg. License LGPL-3.
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerPjp(TransactionCase):
    def test_01_partner_pjp_fields_exist_and_settable(self):
        """Verifikasi bahwa field PJP (call day, frequency, delivery route) tersimpan dengan valid."""
        Partner = self.env["res.partner"].sudo()

        partner = Partner.create({
            "name": "Toko Sejahtera Manado",
            "ref": "OUT-TEST-PJP-01",
            "pjp_call_day": "monday",
            "pjp_frequency": "F1",
            "delivery_route": "RUTE-MND-URBAN-01",
        })

        self.assertEqual(partner.pjp_call_day, "monday")
        self.assertEqual(partner.pjp_frequency, "F1")
        self.assertEqual(partner.delivery_route, "RUTE-MND-URBAN-01")

        # Test update to bi-weekly and tuesday
        partner.write({
            "pjp_call_day": "tuesday",
            "pjp_frequency": "F2",
        })
        self.assertEqual(partner.pjp_call_day, "tuesday")
        self.assertEqual(partner.pjp_frequency, "F2")

    def test_02_partner_pjp_selection_keys(self):
        """Pastikan opsi seleksi pjp_call_day dan pjp_frequency sesuai standar."""
        Partner = self.env["res.partner"]
        day_keys = [k for k, _ in Partner._fields["pjp_call_day"].selection]
        freq_keys = [k for k, _ in Partner._fields["pjp_frequency"].selection]

        self.assertIn("monday", day_keys)
        self.assertIn("saturday", day_keys)
        self.assertIn("F1", freq_keys)
        self.assertIn("F2", freq_keys)
        self.assertIn("F4", freq_keys)

