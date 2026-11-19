package com.kolondam.odooca.field.domain.visit

import com.kolondam.odooca.field.domain.evidence.EvidenceCapture
import com.kolondam.odooca.field.domain.evidence.EvidenceMetadata
import com.kolondam.odooca.field.domain.evidence.EvidenceReceipt
import com.kolondam.odooca.field.domain.evidence.PhotoHash
import com.kolondam.odooca.field.domain.evidence.localRef
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

private const val NOW = 1_790_000_000_000L
private const val CMD = "0b9d6c52-3a41-4f4e-9d0e-2a6a8f1c7e11"
private const val VISIT = "7c1e9a3b-5d2f-4a8e-b1c4-0e6f2d9a8b73"
private const val SESSION = "d3f1a2b4-6c5e-4b7a-8f9d-1a2b3c4d5e6f"
private const val EVID = "5e8f6a7b-1c2d-4e3f-9a4b-6c7d8e9f0a1b"
private val HASH = "ab".repeat(32)

private fun emit(name: String, json: String) {
    System.getProperty("contract.out")?.let { dir ->
        File(dir).mkdirs()
        File(dir, name).writeText(json)
    }
}

/** Semua nama kunci JSON pada sebuah payload. */
private fun keysOf(json: String): Set<String> =
    Regex("\"([A-Za-z_]+)\":").findAll(json).map { it.groupValues[1] }.toSet()

private fun site() = Site(1.4870, 124.8428, 50.0)
private fun fix(ageMs: Long = 10_000, acc: Double = 8.0, lat: Double = 1.4870, lon: Double = 124.8428) =
    Fix(lat, lon, acc, NOW - ageMs)

private fun evidenceRef(ageMs: Long = 20_000, hash: String = HASH) =
    EvidenceRef(EVID, hash, 1.4870, 124.8428, 8.0, NOW - ageMs)

private fun ctx(fix: Fix = fix(), evidence: EvidenceRef? = evidenceRef()) =
    VisitContext(VISIT, SESSION, "2026-11-15", "snap-abc123", "42", site(), fix, evidence)

private fun invalid(r: BuildResult): Set<ProblemCode> = (r as BuildResult.Invalid).problems.map { it.code }.toSet()

class VisitCommandTest {
    @Test
    fun validCheckInProducesContractEnvelope() {
        val r = VisitCommands.checkIn(CMD, NOW, ctx())
        assertIs<BuildResult.Ok>(r)
        assertEquals(CMD, r.clientUuid)
        emit("check_in.json", r.json)
        assertTrue(r.json.startsWith("{\"schema_version\":1,\"client_uuid\":\"$CMD\""))
        assertTrue("\"type\":\"sales.visit.check_in\"" in r.json)
        assertTrue("\"evidence_version\":1" in r.json)
        assertTrue("\"packageHash\":\"$HASH\"" in r.json)
    }

    @Test
    fun payloadContainsOnlyContractKeys() {
        val json = (VisitCommands.checkIn(CMD, NOW, ctx()) as BuildResult.Ok).json
        val allowed = setOf(
            "schema_version", "client_uuid", "occurred_at", "type", "payload", "visit_uuid", "work_session_id",
            "business_date", "snapshot_version", "outlet_id", "site", "latitude", "longitude", "radius", "fix",
            "accuracy", "sampled_at", "evidence_version", "evidence", "id", "packageHash", "capturedAt",
        )
        assertEquals(emptySet(), keysOf(json) - allowed)
    }

    @Test
    fun checkInRequiresEvidence() {
        assertEquals(setOf(ProblemCode.EVIDENCE_REQUIRED), invalid(VisitCommands.checkIn(CMD, NOW, ctx(evidence = null))))
    }

    @Test
    fun staleFixAndStalePhotoAreRejected() {
        assertEquals(setOf(ProblemCode.FIX_STALE), invalid(VisitCommands.checkIn(CMD, NOW, ctx(fix = fix(ageMs = 61_000)))))
        assertEquals(setOf(ProblemCode.PHOTO_STALE), invalid(VisitCommands.checkIn(CMD, NOW, ctx(evidence = evidenceRef(ageMs = 61_000)))))
        assertEquals(setOf(ProblemCode.FIX_FUTURE), invalid(VisitCommands.checkIn(CMD, NOW, ctx(fix = fix(ageMs = -2_000)))))
    }

    @Test
    fun outsideOrUncertainGeofenceIsRejected() {
        // sekitar 111 m ke utara: di luar radius 50 m
        assertEquals(setOf(ProblemCode.OUTSIDE_GEOFENCE), invalid(VisitCommands.checkIn(CMD, NOW, ctx(fix = fix(lat = 1.4880)))))
        // akurasi buruk membuat posisi tidak pasti walau titiknya di tengah
        assertEquals(setOf(ProblemCode.UNCERTAIN_GEOFENCE), invalid(VisitCommands.checkIn(CMD, NOW, ctx(fix = fix(acc = 60.0)))))
    }

    @Test
    fun malformedFieldsAreAllReported() {
        val bad = ctx().copy(visitUuid = "x", businessDate = "2026-02-30", snapshotVersion = " ", outletId = "")
        val codes = invalid(VisitCommands.checkIn("nope", NOW, bad))
        assertTrue(ProblemCode.BAD_UUID in codes && ProblemCode.BAD_DATE in codes && ProblemCode.EMPTY_FIELD in codes)
        assertTrue(ProblemCode.BAD_HASH in invalid(VisitCommands.checkIn(CMD, NOW, ctx(evidence = evidenceRef(hash = "ABC")))))
        assertTrue(ProblemCode.BAD_RADIUS in invalid(VisitCommands.checkIn(CMD, NOW, ctx().copy(site = Site(1.0, 124.0, 500.0)))))
    }

    @Test
    fun checkOutCarriesOutcomeNotesAndOrders() {
        val orderId = "11111111-2222-4333-8444-555555555555"
        val r = VisitCommands.checkOut(CMD, NOW, ctx(), VisitOutcome.ORDER_REQUESTED, "Toko ramai", listOf(orderId))
        assertIs<BuildResult.Ok>(r)
        emit("check_out.json", r.json)
        assertTrue("\"outcome\":\"order_requested\"" in r.json)
        assertTrue("\"order_uuids\":[\"$orderId\"]" in r.json)
    }

    @Test
    fun checkOutWithoutEvidenceIsAllowedButNotesLimited() {
        val ok = VisitCommands.checkOut(CMD, NOW, ctx(evidence = null), VisitOutcome.NO_ORDER, "", emptyList())
        assertIs<BuildResult.Ok>(ok)
        assertFalse("\"evidence\"" in (ok as BuildResult.Ok).json)
        val long = VisitCommands.checkOut(CMD, NOW, ctx(), VisitOutcome.NO_ORDER, "x".repeat(501), emptyList())
        assertEquals(setOf(ProblemCode.NOTES_TOO_LONG), invalid(long))
        val badOrder = VisitCommands.checkOut(CMD, NOW, ctx(), VisitOutcome.NO_ORDER, "", listOf("bukan-uuid"))
        assertEquals(setOf(ProblemCode.BAD_UUID), invalid(badOrder))
    }

    @Test
    fun jsonEscapesNotes() {
        val r = VisitCommands.checkOut(CMD, NOW, ctx(), VisitOutcome.UNAVAILABLE, "kata \"sandi\"\nbaris", emptyList())
        assertTrue("\"notes\":\"kata \\\"sandi\\\"\\nbaris\"" in (r as BuildResult.Ok).json)
    }
}

class EvidenceMetadataTest {
    private fun capture(
        photoAge: Long = 20_000,
        deviceAge: Long = 10_000,
        fixAge: Long = 10_000,
        outletId: String = "42",
        lat: Double = 1.4870,
    ) = EvidenceCapture(
        clientUuid = EVID, outletId = outletId, businessDate = "2026-11-15", snapshotVersion = "snap-abc123",
        photoSelectedAtMs = NOW - photoAge, deviceRecordedAtMs = NOW - deviceAge,
        fix = fix(ageMs = fixAge, lat = lat), site = site(),
    )

    @Test
    fun validCaptureProducesContractMetadataWithoutMode() {
        val r = EvidenceMetadata.build(capture(), NOW)
        assertIs<BuildResult.Ok>(r)
        emit("evidence_metadata.json", r.json)
        assertTrue(r.json.startsWith("{\"client_uuid\":\"$EVID\",\"outlet_id\":\"42\""))
        val allowed = setOf(
            "client_uuid", "outlet_id", "business_date", "snapshot_version", "photo_selected_at",
            "device_recorded_at", "fix_sampled_at", "latitude", "longitude", "accuracy",
        )
        assertEquals(allowed, keysOf(r.json))
    }

    @Test
    fun outletIdMustBeNumeric() {
        assertEquals(setOf(ProblemCode.BAD_OUTLET_ID), invalid(EvidenceMetadata.build(capture(outletId = "OUT-7"), NOW)))
    }

    @Test
    fun timingRulesMatchServerWindows() {
        assertEquals(setOf(ProblemCode.PHOTO_STALE), invalid(EvidenceMetadata.build(capture(photoAge = 301_000), NOW)))
        assertEquals(setOf(ProblemCode.DEVICE_STALE), invalid(EvidenceMetadata.build(capture(deviceAge = 61_000), NOW)))
        assertEquals(setOf(ProblemCode.FIX_STALE), invalid(EvidenceMetadata.build(capture(fixAge = 61_000), NOW)))
        assertEquals(
            setOf(ProblemCode.PHOTO_AFTER_DEVICE_RECORD),
            invalid(EvidenceMetadata.build(capture(photoAge = 10_000, deviceAge = 20_000), NOW)),
        )
    }

    @Test
    fun outsideGeofenceIsRejectedBeforeUpload() {
        assertEquals(setOf(ProblemCode.OUTSIDE_GEOFENCE), invalid(EvidenceMetadata.build(capture(lat = 1.4880), NOW)))
    }

    @Test
    fun receiptBecomesCheckInReferenceUsingBindingHash() {
        val receipt = EvidenceReceipt(EVID, HASH, "cd".repeat(32), "ef".repeat(32), 1.4870, 124.8428, 8.0, NOW - 15_000)
        val ref = receipt.toRef()
        assertEquals(HASH, ref.packageHash)
        assertEquals(EVID, ref.id)
        assertEquals(NOW - 15_000, ref.capturedAtMs)
        assertIs<BuildResult.Ok>(VisitCommands.checkIn(CMD, NOW, ctx(evidence = ref)))
    }
}

class PhotoHashTest {
    @Test
    fun knownSha256Vectors() {
        assertEquals(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            PhotoHash.sha256Hex(ByteArray(0)),
        )
        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            PhotoHash.sha256Hex("abc".toByteArray()),
        )
    }

    @Test
    fun localReferenceCarriesCaptureData() {
        val capture = EvidenceCapture(
            EVID, "42", "2026-11-15", "snap-abc123", NOW - 20_000, NOW - 10_000, fix(), site(),
        )
        val hash = PhotoHash.sha256Hex("foto".toByteArray())
        val ref = capture.localRef(hash)
        assertEquals(hash, ref.packageHash)
        assertEquals(EVID, ref.id)
        assertIs<BuildResult.Ok>(VisitCommands.checkIn(CMD, NOW, ctx(evidence = ref)))
    }
}
