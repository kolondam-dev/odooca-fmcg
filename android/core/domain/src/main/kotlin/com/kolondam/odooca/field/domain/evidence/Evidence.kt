package com.kolondam.odooca.field.domain.evidence

import com.kolondam.odooca.field.domain.geo.EvidenceTiming
import com.kolondam.odooca.field.domain.geo.TimingStatus
import com.kolondam.odooca.field.domain.json.jsonObject
import com.kolondam.odooca.field.domain.time.Iso
import com.kolondam.odooca.field.domain.visit.BuildResult
import com.kolondam.odooca.field.domain.visit.Checks
import com.kolondam.odooca.field.domain.visit.EvidenceRef
import com.kolondam.odooca.field.domain.visit.Fix
import com.kolondam.odooca.field.domain.visit.Problem
import com.kolondam.odooca.field.domain.visit.ProblemCode
import com.kolondam.odooca.field.domain.visit.Site

/** Data pengambilan satu foto bukti resmi sebelum diunggah. */
data class EvidenceCapture(
    val clientUuid: String,
    val outletId: String,
    val businessDate: String,
    val snapshotVersion: String,
    val photoSelectedAtMs: Long,
    val deviceRecordedAtMs: Long,
    val fix: Fix,
    val site: Site,
)

/** Receipt `POST /api/v1/evidence` (bagian yang dipakai klien). */
data class EvidenceReceipt(
    val clientUuid: String,
    val bindingSha256: String,
    val originalSha256: String,
    val watermarkedSha256: String,
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double,
    val photoSelectedAtMs: Long,
) {
    /** Rujukan untuk payload check-in: `packageHash` memakai `binding_sha256`. */
    fun toRef() = EvidenceRef(
        id = clientUuid,
        packageHash = bindingSha256,
        latitude = latitude,
        longitude = longitude,
        accuracyM = accuracyM,
        capturedAtMs = photoSelectedAtMs,
    )
}

object EvidenceMetadata {
    const val MAX_ACCURACY_M = 10_000.0

    /**
     * Metadata multipart untuk `POST /api/v1/evidence`. Klien native tidak pernah mengirim
     * field `mode`: pelonggaran gerbang, bila ada, diputuskan server.
     */
    fun build(capture: EvidenceCapture, nowMs: Long): BuildResult {
        val c = Checks()
        c.uuid("client_uuid", capture.clientUuid)
        if (!OUTLET_NUMERIC.matches(capture.outletId)) {
            c.problems += Problem(ProblemCode.BAD_OUTLET_ID, "outlet_id", "outlet_id bukti harus angka")
        }
        c.date("business_date", capture.businessDate)
        c.nonBlank("snapshot_version", capture.snapshotVersion)
        val siteOk = c.site(capture.site)
        c.accuracyPositive("accuracy", capture.fix.accuracyM, MAX_ACCURACY_M)

        when (EvidenceTiming.assess(nowMs, capture.fix.sampledAtMs, capture.photoSelectedAtMs, capture.deviceRecordedAtMs)) {
            TimingStatus.OK -> Unit
            TimingStatus.FIX_FUTURE -> c.problems += Problem(ProblemCode.FIX_FUTURE, "fix_sampled_at", "Waktu fix lebih maju dari jam server")
            TimingStatus.FIX_STALE -> c.problems += Problem(ProblemCode.FIX_STALE, "fix_sampled_at", "Lokasi lebih dari 60 detik")
            TimingStatus.PHOTO_FUTURE -> c.problems += Problem(ProblemCode.PHOTO_FUTURE, "photo_selected_at", "Waktu foto lebih maju dari jam server")
            TimingStatus.PHOTO_STALE -> c.problems += Problem(ProblemCode.PHOTO_STALE, "photo_selected_at", "Foto lebih dari 300 detik")
            TimingStatus.DEVICE_FUTURE -> c.problems += Problem(ProblemCode.DEVICE_FUTURE, "device_recorded_at", "Catatan perangkat lebih maju dari jam server")
            TimingStatus.DEVICE_STALE -> c.problems += Problem(ProblemCode.DEVICE_STALE, "device_recorded_at", "Catatan perangkat lebih dari 60 detik")
            TimingStatus.PHOTO_AFTER_DEVICE_RECORD -> c.problems += Problem(ProblemCode.PHOTO_AFTER_DEVICE_RECORD, "photo_selected_at", "Foto dipilih setelah catatan perangkat dibuat")
        }
        c.fixInsideSite(nowMs, capture.fix, capture.site, siteOk)
        // fixInsideSite juga memeriksa kesegaran fix; satu masalah per kode saja.
        val unique = c.problems.distinctBy { it.code }
        if (unique.isNotEmpty()) return BuildResult.Invalid(unique)

        val json = jsonObject {
            put("client_uuid", capture.clientUuid)
            put("outlet_id", capture.outletId)
            put("business_date", capture.businessDate)
            put("snapshot_version", capture.snapshotVersion)
            put("photo_selected_at", Iso.formatUtc(capture.photoSelectedAtMs))
            put("device_recorded_at", Iso.formatUtc(capture.deviceRecordedAtMs))
            put("fix_sampled_at", Iso.formatUtc(capture.fix.sampledAtMs))
            put("latitude", capture.fix.latitude)
            put("longitude", capture.fix.longitude)
            put("accuracy", capture.fix.accuracyM)
        }
        return BuildResult.Ok(capture.clientUuid, json)
    }

    private val OUTLET_NUMERIC = Regex("^\\d+$")
}
