from odoo import models


class MobileWorkday(models.Model):
    _inherit = "id.mobile.workday"

    def _snapshot_payload(self, include_volatile=True):
        result = super()._snapshot_payload(include_volatile=include_volatile)
        if include_volatile:
            # BE-20c: SJP berubah setiap terbit/pembayaran, jadi di luar digest versi (seperti piutang/tier):
            # digest sudah dihitung oleh super(); blok ini tidak masuk command/evidence (include_volatile=False).
            assignment, day = self._current_assignment()
            result["collection_sheets"] = self.env["id.collection.sheet"]._mobile_snapshot_payload(
                assignment.with_company(assignment.company_id), day
            )
        return result
