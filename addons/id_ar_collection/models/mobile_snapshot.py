from odoo import models


class MobileWorkday(models.Model):
    _inherit = "id.mobile.workday"

    def _snapshot_payload(self, include_volatile=True):
        if not include_volatile:
            return super()._snapshot_payload(include_volatile=False)
        # BE-20c: satu jangkar (assignment, hari) untuk seluruh snapshot. Bila hari WITA berganti di tengah
        # request, respons ditolak (MobileReadConflict) dan tidak pernah berupa campuran dua hari.
        assignment, day = self._current_assignment()
        result = super()._snapshot_payload(include_volatile=True)
        assignment._assert_day(day)  # induk mungkin sudah memakai hari lain; tolak sebelum SJP disisipkan
        # SJP berubah setiap terbit/pembayaran, jadi di luar digest versi (seperti piutang/tier):
        # digest sudah dihitung oleh super(); blok ini tidak masuk command/evidence (include_volatile=False).
        result["collection_sheets"] = self.env["id.collection.sheet"]._mobile_snapshot_payload(
            assignment.with_company(assignment.company_id), day
        )
        assignment._assert_day(day)  # validasi akhir setelah blok SJP selesai
        return result
