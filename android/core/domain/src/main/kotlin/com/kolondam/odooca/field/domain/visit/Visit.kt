package com.kolondam.odooca.field.domain.visit

import com.kolondam.odooca.field.domain.geo.EvidenceTiming
import com.kolondam.odooca.field.domain.geo.GeoMath
import com.kolondam.odooca.field.domain.geo.Geofence
import com.kolondam.odooca.field.domain.geo.GeofenceStatus
import com.kolondam.odooca.field.domain.json.jsonObject
import com.kolondam.odooca.field.domain.time.Iso

data class Fix(val latitude: Double, val longitude: Double, val accuracyM: Double, val sampledAtMs: Long)

data class Site(val latitude: Double, val longitude: Double, val radiusM: Double)

/** Rujukan bukti yang sudah diterima server. `packageHash` = `binding_sha256` pada receipt evidence. */
data class EvidenceRef(
    val id: String,
    val packageHash: String,
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double,
    val capturedAtMs: Long,
)

enum class VisitOutcome(val wire: String) {
    ORDER_REQUESTED("order_requested"),
    NO_ORDER("no_order"),
    OUTLET_CLOSED("outlet_closed"),
    UNAVAILABLE("unavailable"),
}

data class VisitContext(
    val visitUuid: String,
    val workSessionId: String,
    val businessDate: String,
    val snapshotVersion: String,
    val outletId: String,
    val site: Site,
    val fix: Fix,
    val evidence: EvidenceRef?,
)

enum class ProblemCode {
    BAD_UUID, BAD_DATE, EMPTY_FIELD, BAD_COORDINATE, BAD_ACCURACY, BAD_RADIUS,
    FIX_STALE, FIX_FUTURE, PHOTO_STALE, PHOTO_FUTURE,
    OUTSIDE_GEOFENCE, UNCERTAIN_GEOFENCE,
    EVIDENCE_REQUIRED, BAD_HASH, NOTES_TOO_LONG, BAD_OUTLET_ID,
    DEVICE_STALE, DEVICE_FUTURE, PHOTO_AFTER_DEVICE_RECORD,
}

data class Problem(val code: ProblemCode, val field: String, val message: String)

sealed interface BuildResult {
    data class Ok(val clientUuid: String, val json: String) : BuildResult
    data class Invalid(val problems: List<Problem>) : BuildResult
}

/** Aturan validasi bersama untuk payload yang dikirim ke server. */
internal class Checks {
    val problems = ArrayList<Problem>()

    fun uuid(field: String, value: String) {
        if (!UUID.matches(value)) problems += Problem(ProblemCode.BAD_UUID, field, "UUID tidak valid")
    }

    fun nonBlank(field: String, value: String) {
        if (value.isBlank()) problems += Problem(ProblemCode.EMPTY_FIELD, field, "Tidak boleh kosong")
    }

    fun date(field: String, value: String) {
        if (!Iso.isValidDate(value)) problems += Problem(ProblemCode.BAD_DATE, field, "Tanggal harus yyyy-MM-dd yang valid")
    }

    fun coordinate(field: String, lat: Double, lon: Double): Boolean {
        val ok = lat.isFinite() && lon.isFinite() && lat in -90.0..90.0 && lon in -180.0..180.0
        if (!ok) problems += Problem(ProblemCode.BAD_COORDINATE, field, "Koordinat di luar rentang")
        return ok
    }

    fun accuracyPositive(field: String, value: Double, max: Double = Double.MAX_VALUE): Boolean {
        val ok = value.isFinite() && value > 0.0 && value <= max
        if (!ok) problems += Problem(ProblemCode.BAD_ACCURACY, field, "Akurasi harus > 0 dan wajar")
        return ok
    }

    fun site(site: Site): Boolean {
        val coordOk = coordinate("site", site.latitude, site.longitude)
        val radiusOk = site.radiusM.isFinite() && site.radiusM in Geofence.MIN_RADIUS_M..Geofence.MAX_OUTLET_RADIUS_M
        if (!radiusOk) problems += Problem(ProblemCode.BAD_RADIUS, "site.radius", "Radius harus 5 sampai 150 m")
        return coordOk && radiusOk
    }

    /** Fix harus segar dan berada di dalam radius situs. Server menolak yang lain. */
    fun fixInsideSite(nowMs: Long, fix: Fix, site: Site, siteOk: Boolean) {
        val coordOk = coordinate("fix", fix.latitude, fix.longitude)
        val accOk = accuracyPositive("fix.accuracy", fix.accuracyM)
        val age = nowMs - fix.sampledAtMs
        if (age < -EvidenceTiming.FIX_MAX_AHEAD_MS) problems += Problem(ProblemCode.FIX_FUTURE, "fix.sampled_at", "Waktu fix lebih maju dari jam server")
        if (age > EvidenceTiming.FIX_MAX_AGE_MS) problems += Problem(ProblemCode.FIX_STALE, "fix.sampled_at", "Lokasi lebih dari 60 detik")
        if (coordOk && accOk && siteOk) {
            val distance = GeoMath.distanceMeters(fix.latitude, fix.longitude, site.latitude, site.longitude)
            when (Geofence.assess(distance, fix.accuracyM, site.radiusM)) {
                GeofenceStatus.INSIDE -> Unit
                GeofenceStatus.OUTSIDE -> problems += Problem(ProblemCode.OUTSIDE_GEOFENCE, "fix", "Di luar radius outlet")
                GeofenceStatus.UNCERTAIN -> problems += Problem(ProblemCode.UNCERTAIN_GEOFENCE, "fix", "Posisi belum pasti di dalam radius")
            }
        }
    }

    fun evidence(nowMs: Long, e: EvidenceRef) {
        uuid("evidence.id", e.id)
        if (!HASH.matches(e.packageHash)) problems += Problem(ProblemCode.BAD_HASH, "evidence.packageHash", "Hash harus 64 heksadesimal huruf kecil")
        coordinate("evidence", e.latitude, e.longitude)
        if (!(e.accuracyM.isFinite() && e.accuracyM >= 0.0)) problems += Problem(ProblemCode.BAD_ACCURACY, "evidence.accuracy", "Akurasi bukti tidak valid")
        val age = nowMs - e.capturedAtMs
        if (age < -EvidenceTiming.PHOTO_MAX_AHEAD_MS) problems += Problem(ProblemCode.PHOTO_FUTURE, "evidence.capturedAt", "Waktu foto lebih maju dari jam server")
        if (age > VisitCommands.EVIDENCE_MAX_AGE_AT_COMMAND_MS) problems += Problem(ProblemCode.PHOTO_STALE, "evidence.capturedAt", "Foto lebih dari 60 detik")
    }

    companion object {
        val UUID = Regex("^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)$")
        val HASH = Regex("^[a-f0-9]{64}$")
    }
}

object VisitCommands {
    const val NOTES_MAX = 500

    /** Klien web mensyaratkan foto check-in berumur paling lama 60 detik saat command dibuat. */
    const val EVIDENCE_MAX_AGE_AT_COMMAND_MS = 60_000L

    fun checkIn(commandUuid: String, nowMs: Long, ctx: VisitContext): BuildResult {
        val c = Checks()
        c.uuid("client_uuid", commandUuid)
        validateContext(c, nowMs, ctx)
        val evidence = ctx.evidence
        if (evidence == null) {
            c.problems += Problem(ProblemCode.EVIDENCE_REQUIRED, "evidence", "Check-in wajib menyertakan bukti foto")
        } else {
            c.evidence(nowMs, evidence)
        }
        if (c.problems.isNotEmpty()) return BuildResult.Invalid(c.problems)
        return BuildResult.Ok(commandUuid, envelope(commandUuid, nowMs, "sales.visit.check_in", ctx, null))
    }

    fun checkOut(
        commandUuid: String,
        nowMs: Long,
        ctx: VisitContext,
        outcome: VisitOutcome,
        notes: String,
        orderUuids: List<String>,
    ): BuildResult {
        val c = Checks()
        c.uuid("client_uuid", commandUuid)
        validateContext(c, nowMs, ctx)
        ctx.evidence?.let { c.evidence(nowMs, it) }
        if (notes.length > NOTES_MAX) c.problems += Problem(ProblemCode.NOTES_TOO_LONG, "notes", "Catatan maksimal 500 karakter")
        orderUuids.forEachIndexed { i, id -> c.uuid("order_uuids[$i]", id) }
        if (c.problems.isNotEmpty()) return BuildResult.Invalid(c.problems)
        return BuildResult.Ok(
            commandUuid,
            envelope(commandUuid, nowMs, "sales.visit.check_out", ctx, Triple(outcome, notes, orderUuids)),
        )
    }

    private fun validateContext(c: Checks, nowMs: Long, ctx: VisitContext) {
        c.uuid("visit_uuid", ctx.visitUuid)
        c.uuid("work_session_id", ctx.workSessionId)
        c.date("business_date", ctx.businessDate)
        c.nonBlank("snapshot_version", ctx.snapshotVersion)
        c.nonBlank("outlet_id", ctx.outletId)
        val siteOk = c.site(ctx.site)
        c.fixInsideSite(nowMs, ctx.fix, ctx.site, siteOk)
    }

    private fun envelope(
        commandUuid: String,
        nowMs: Long,
        type: String,
        ctx: VisitContext,
        closing: Triple<VisitOutcome, String, List<String>>?,
    ): String = jsonObject {
        put("schema_version", 1)
        put("client_uuid", commandUuid)
        put("occurred_at", Iso.formatUtc(nowMs))
        put("type", type)
        putObject("payload") {
            put("visit_uuid", ctx.visitUuid)
            put("work_session_id", ctx.workSessionId)
            put("business_date", ctx.businessDate)
            put("snapshot_version", ctx.snapshotVersion)
            put("outlet_id", ctx.outletId)
            putObject("site") {
                put("latitude", ctx.site.latitude)
                put("longitude", ctx.site.longitude)
                put("radius", ctx.site.radiusM)
            }
            putObject("fix") {
                put("latitude", ctx.fix.latitude)
                put("longitude", ctx.fix.longitude)
                put("accuracy", ctx.fix.accuracyM)
                put("sampled_at", Iso.formatUtc(ctx.fix.sampledAtMs))
            }
            ctx.evidence?.let { e ->
                put("evidence_version", 1)
                putObject("evidence") {
                    put("id", e.id)
                    put("packageHash", e.packageHash)
                    put("latitude", e.latitude)
                    put("longitude", e.longitude)
                    put("accuracy", e.accuracyM)
                    put("capturedAt", Iso.formatUtc(e.capturedAtMs))
                }
            }
            if (closing != null) {
                put("outcome", closing.first.wire)
                put("notes", closing.second)
                putStrings("order_uuids", closing.third)
            }
        }
    }
}
