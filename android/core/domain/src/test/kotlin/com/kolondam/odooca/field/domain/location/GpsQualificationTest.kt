package com.kolondam.odooca.field.domain.location

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class GpsQualificationTest {
    private val sessionStart = 1_000_000L
    private val base = 1.4870 to 124.8428

    private fun samples(
        count: Int,
        accuracy: Double = 8.0,
        firstFixAfterMs: Long = 10_000,
        stepMs: Long = 5_000,
    ): List<LocationSample> = List(count) { i ->
        LocationSample(
            latitude = base.first + (i % 3) * 0.00001,
            longitude = base.second + (i % 2) * 0.00001,
            accuracyM = accuracy,
            timestampMs = sessionStart + firstFixAfterMs + i * stepMs,
            provider = "gps",
        )
    }

    private fun input(
        s: List<LocationSample>,
        permission: Boolean = true,
        services: Boolean = true,
        integrity: IntegritySignals = IntegritySignals(appIntegrity = AppIntegrity.PASS),
    ) = CalibrationInput(
        samples = s,
        nowMs = (s.maxOfOrNull { it.timestampMs } ?: sessionStart) + 1_000,
        sessionStartMs = sessionStart,
        permissionGranted = permission,
        locationServicesEnabled = services,
        integrity = integrity,
    )

    @Test
    fun cleanStaticSessionIsQualifiedAndTrusted() {
        val r = GpsQualification.evaluate(input(samples(12)))
        assertEquals(100, r.total)
        assertEquals(QualificationCategory.QUALIFIED, r.category)
        assertEquals(LocationStatus.TRUSTED, r.status)
        assertTrue(r.reasons.isEmpty(), "alasan=${r.reasons}")
        assertEquals("hipotesis-v0", r.policyVersion)
        assertEquals(12, r.metrics.validSamples)
        assertEquals(10_000L, r.metrics.firstFixMs)
    }

    @Test
    fun unavailableAppIntegrityCapsCategoryAtConditional() {
        val r = GpsQualification.evaluate(
            input(samples(12), integrity = IntegritySignals(appIntegrity = AppIntegrity.UNAVAILABLE)),
        )
        assertEquals(90, r.total)
        assertEquals(QualificationCategory.CONDITIONAL, r.category)
        assertEquals(LocationStatus.INTEGRITY_UNAVAILABLE, r.status)
        assertTrue(QualificationReason.APP_INTEGRITY_UNAVAILABLE in r.reasons)
    }

    @Test
    fun spoofingFlagIsAHardGateRegardlessOfScore() {
        val r = GpsQualification.evaluate(
            input(samples(12), integrity = IntegritySignals(spoofingFlagged = true, appIntegrity = AppIntegrity.PASS)),
        )
        assertEquals(QualificationCategory.UNQUALIFIED, r.category)
        assertEquals(LocationStatus.SPOOFING_DETECTED, r.status)
        assertTrue(QualificationReason.SPOOFING_FLAGGED in r.reasons)
    }

    @Test
    fun missingPermissionIsUnqualified() {
        val r = GpsQualification.evaluate(input(emptyList(), permission = false))
        assertEquals(LocationStatus.PERMISSION_DENIED, r.status)
        assertEquals(QualificationCategory.UNQUALIFIED, r.category)
        assertTrue(QualificationReason.PERMISSION_DENIED in r.reasons)
        assertTrue(QualificationReason.NO_FIX in r.reasons)
    }

    @Test
    fun locationServicesOffReportsPermissionDeniedGroup() {
        val r = GpsQualification.evaluate(input(samples(12), services = false))
        assertEquals(LocationStatus.PERMISSION_DENIED, r.status)
        assertTrue(QualificationReason.LOCATION_SERVICES_OFF in r.reasons)
    }

    @Test
    fun tooFewSamplesIsLowAccuracyAndUnqualified() {
        val r = GpsQualification.evaluate(input(samples(5)))
        assertEquals(LocationStatus.LOW_ACCURACY, r.status)
        assertEquals(QualificationCategory.UNQUALIFIED, r.category)
        assertTrue(QualificationReason.INSUFFICIENT_SAMPLES in r.reasons)
    }

    @Test
    fun poorAccuracyIsLowAccuracy() {
        val r = GpsQualification.evaluate(input(samples(12, accuracy = 60.0)))
        assertEquals(LocationStatus.LOW_ACCURACY, r.status)
        assertTrue(QualificationReason.ACCURACY_TOO_LOW in r.reasons)
        assertEquals(QualificationCategory.UNQUALIFIED, r.category)
    }

    @Test
    fun mediocreAccuracyScoresConditionalButStillTrustedStatus() {
        val r = GpsQualification.evaluate(input(samples(12, accuracy = 40.0)))
        assertEquals(79, r.total)
        assertEquals(QualificationCategory.CONDITIONAL, r.category)
        assertEquals(LocationStatus.TRUSTED, r.status)
    }

    @Test
    fun rootIndicatorsMarkSuspiciousAndLowerIntegrity() {
        val r = GpsQualification.evaluate(
            input(samples(12), integrity = IntegritySignals(rootOrHookingIndicators = true, appIntegrity = AppIntegrity.PASS)),
        )
        assertEquals(LocationStatus.SUSPICIOUS, r.status)
        assertEquals(0.0, r.integrityPoints, 1e-9)
        assertEquals(80, r.total)
        assertEquals(QualificationCategory.CONDITIONAL, r.category)
    }

    @Test
    fun appIntegrityFailureIsSuspicious() {
        val r = GpsQualification.evaluate(
            input(samples(12), integrity = IntegritySignals(appIntegrity = AppIntegrity.FAIL)),
        )
        assertEquals(LocationStatus.SUSPICIOUS, r.status)
        assertTrue(QualificationReason.APP_INTEGRITY_FAILED in r.reasons)
    }

    @Test
    fun futureTimestampZeroesTimestampPoints() {
        val s = samples(12)
        val future = s.toMutableList().also { it[11] = it[11].copy(timestampMs = it[11].timestampMs + 60_000) }
        val r = GpsQualification.evaluate(input(future).copy(nowMs = s.last().timestampMs + 1_000))
        assertEquals(0.0, r.timestampPoints, 1e-9)
        assertTrue(QualificationReason.FUTURE_TIMESTAMP in r.reasons)
    }

    @Test
    fun largeGapReducesTimestampPointsProportionally() {
        val s = samples(12).toMutableList()
        for (i in 6 until 12) s[i] = s[i].copy(timestampMs = s[i].timestampMs + 40_000)
        val r = GpsQualification.evaluate(input(s))
        assertTrue(QualificationReason.SAMPLE_GAP in r.reasons)
        // 1 transisi buruk dari 11
        assertEquals(10.0 * (1.0 - 1.0 / 11.0), r.timestampPoints, 1e-9)
    }

    @Test
    fun outOfOrderTimestampsAreFlagged() {
        val s = samples(12).toMutableList()
        s[5] = s[5].copy(timestampMs = s[3].timestampMs - 1_000)
        val r = GpsQualification.evaluate(input(s))
        assertTrue(QualificationReason.NON_MONOTONIC_TIMESTAMP in r.reasons)
    }

    @Test
    fun invalidSamplesAreIgnored() {
        val s = samples(12) + LocationSample(95.0, 124.0, 5.0, sessionStart + 100_000, "gps") +
            LocationSample(1.0, 124.0, -3.0, sessionStart + 105_000, "gps")
        val r = GpsQualification.evaluate(input(s))
        assertEquals(14, r.metrics.totalSamples)
        assertEquals(12, r.metrics.validSamples)
    }

    @Test
    fun weightsMustSumToHundred() {
        assertFailsWith<IllegalArgumentException> { DimensionWeights(accuracy = 31) }
    }

    @Test
    fun medianAndPercentileUtilities() {
        assertNull(GpsQualification.median(emptyList()))
        assertEquals(3.0, GpsQualification.median(listOf(5.0, 1.0, 3.0))!!, 1e-9)
        assertEquals(2.5, GpsQualification.median(listOf(1.0, 2.0, 3.0, 4.0))!!, 1e-9)
        val ten = (1..10).map { it.toDouble() }
        assertEquals(9.0, GpsQualification.percentile(ten, 0.9)!!, 1e-9)
        assertEquals(1.0, GpsQualification.percentile(ten, 0.0)!!, 1e-9)
        assertEquals(1.0, GpsQualification.linear(10.0, 15.0, 50.0), 1e-9)
        assertEquals(0.0, GpsQualification.linear(60.0, 15.0, 50.0), 1e-9)
    }
}

class GpsAccuracyGateTest {
    private fun run(accuracies: List<Double>): QualificationReport {
        val start = 1_000_000L
        val s = accuracies.mapIndexed { i, a ->
            LocationSample(1.4870 + (i % 3) * 0.00001, 124.8428, a, start + 10_000 + i * 5_000L, "gps")
        }
        return GpsQualification.evaluate(
            CalibrationInput(s, s.last().timestampMs + 1_000, start, true, true,
                IntegritySignals(appIntegrity = AppIntegrity.PASS)),
        )
    }

    @Test
    fun p90BeyondLimitFailsEvenWhenMedianIsGood() {
        // median 10 m, tetapi 2 dari 12 sampel sangat buruk -> P90 = 150 m
        val r = run(List(10) { 10.0 } + listOf(150.0, 150.0))
        assertEquals(LocationStatus.LOW_ACCURACY, r.status)
        assertEquals(QualificationCategory.UNQUALIFIED, r.category)
        assertTrue(QualificationReason.ACCURACY_TOO_LOW in r.reasons)
    }

    @Test
    fun goodMedianAndP90PassesGate() {
        val r = run(List(12) { 12.0 })
        assertEquals(LocationStatus.TRUSTED, r.status)
    }
}
