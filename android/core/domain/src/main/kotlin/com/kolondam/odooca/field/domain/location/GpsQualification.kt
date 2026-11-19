package com.kolondam.odooca.field.domain.location

import com.kolondam.odooca.field.domain.geo.GeoMath
import kotlin.math.ceil
import kotlin.math.roundToInt

/** Satu sampel lokasi dari perangkat. Waktu dalam epoch milidetik. */
data class LocationSample(
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double,
    val timestampMs: Long,
    val provider: String,
)

enum class AppIntegrity { PASS, FAIL, UNAVAILABLE }

/** Sinyal integritas yang dikumpulkan lapisan perangkat. */
data class IntegritySignals(
    /** Android menandai lokasi berasal dari provider buatan (pemalsuan lokasi). */
    val spoofingFlagged: Boolean = false,
    val developerOptionsEnabled: Boolean? = null,
    val rootOrHookingIndicators: Boolean = false,
    val appIntegrity: AppIntegrity = AppIntegrity.UNAVAILABLE,
)

data class CalibrationInput(
    val samples: List<LocationSample>,
    val nowMs: Long,
    val sessionStartMs: Long,
    val permissionGranted: Boolean,
    val locationServicesEnabled: Boolean,
    val integrity: IntegritySignals = IntegritySignals(),
)

enum class QualificationCategory { QUALIFIED, CONDITIONAL, UNQUALIFIED }

/** Status terstruktur yang dilaporkan ke backend. Keputusan akhir ada di server. */
enum class LocationStatus {
    TRUSTED,
    SUSPICIOUS,
    SPOOFING_DETECTED,
    LOW_ACCURACY,
    PERMISSION_DENIED,
    INTEGRITY_UNAVAILABLE,
    DEVICE_UNQUALIFIED,
}

enum class QualificationReason {
    PERMISSION_DENIED, LOCATION_SERVICES_OFF, NO_FIX, INSUFFICIENT_SAMPLES,
    SPOOFING_FLAGGED, ROOT_OR_HOOKING, APP_INTEGRITY_FAILED, APP_INTEGRITY_UNAVAILABLE,
    FUTURE_TIMESTAMP, NON_MONOTONIC_TIMESTAMP, SAMPLE_GAP,
    ACCURACY_TOO_LOW, UNSTABLE_POSITION, SLOW_FIRST_FIX,
}

data class DimensionWeights(
    val accuracy: Int = 30,
    val firstFix: Int = 15,
    val stability: Int = 25,
    val timestamps: Int = 10,
    val integrity: Int = 20,
) {
    init {
        require(accuracy + firstFix + stability + timestamps + integrity == 100) { "Bobot harus berjumlah 100" }
    }
}

/**
 * Kebijakan kualifikasi. Seluruh ambang adalah HIPOTESIS awal dari blueprint dan wajib
 * dikalibrasi dari uji lapangan di perangkat target sebelum dipakai sebagai keputusan.
 * `version` ikut dikirim ke backend agar hasil dapat dikaitkan dengan kebijakan yang dipakai.
 */
data class QualificationPolicy(
    val version: String = "hipotesis-v0",
    val minSamples: Int = 8,
    val medianAccuracyFullM: Double = 15.0,
    val medianAccuracyZeroM: Double = 50.0,
    val p90AccuracyFullM: Double = 30.0,
    val p90AccuracyZeroM: Double = 100.0,
    val firstFixFullMs: Long = 30_000,
    val firstFixZeroMs: Long = 120_000,
    val displacementFullM: Double = 15.0,
    val displacementZeroM: Double = 60.0,
    val maxSampleGapMs: Long = 30_000,
    val maxFutureSkewMs: Long = 2_000,
    val weights: DimensionWeights = DimensionWeights(),
    val qualifiedMin: Int = 85,
    val conditionalMin: Int = 70,
)

data class QualificationMetrics(
    val totalSamples: Int,
    val validSamples: Int,
    val medianAccuracyM: Double?,
    val p90AccuracyM: Double?,
    val firstFixMs: Long?,
    val medianDisplacementM: Double?,
)

data class QualificationReport(
    val policyVersion: String,
    val accuracyPoints: Double,
    val firstFixPoints: Double,
    val stabilityPoints: Double,
    val timestampPoints: Double,
    val integrityPoints: Double,
    val total: Int,
    val category: QualificationCategory,
    val status: LocationStatus,
    val reasons: List<QualificationReason>,
    val metrics: QualificationMetrics,
)

object GpsQualification {
    fun evaluate(input: CalibrationInput, policy: QualificationPolicy = QualificationPolicy()): QualificationReport {
        val reasons = linkedSetOf<QualificationReason>()
        val valid = input.samples.filter(::isValid)

        val medianAcc = median(valid.map { it.accuracyM })
        val p90Acc = percentile(valid.map { it.accuracyM }, 0.9)
        val firstFix = valid.minOfOrNull { it.timestampMs }?.let { it - input.sessionStartMs }?.coerceAtLeast(0)
        val displacement = medianDisplacement(valid)

        if (!input.permissionGranted) reasons += QualificationReason.PERMISSION_DENIED
        if (!input.locationServicesEnabled) reasons += QualificationReason.LOCATION_SERVICES_OFF
        if (valid.isEmpty()) reasons += QualificationReason.NO_FIX
        else if (valid.size < policy.minSamples) reasons += QualificationReason.INSUFFICIENT_SAMPLES
        if (input.integrity.spoofingFlagged) reasons += QualificationReason.SPOOFING_FLAGGED
        if (input.integrity.rootOrHookingIndicators) reasons += QualificationReason.ROOT_OR_HOOKING
        when (input.integrity.appIntegrity) {
            AppIntegrity.FAIL -> reasons += QualificationReason.APP_INTEGRITY_FAILED
            AppIntegrity.UNAVAILABLE -> reasons += QualificationReason.APP_INTEGRITY_UNAVAILABLE
            AppIntegrity.PASS -> Unit
        }

        val sufficiency = if (valid.isEmpty()) 0.0 else minOf(1.0, valid.size.toDouble() / policy.minSamples)

        val accuracyRatio = if (medianAcc == null || p90Acc == null) 0.0 else {
            val r = minOf(
                linear(medianAcc, policy.medianAccuracyFullM, policy.medianAccuracyZeroM),
                linear(p90Acc, policy.p90AccuracyFullM, policy.p90AccuracyZeroM),
            )
            if (accuracyBeyondLimit(medianAcc, p90Acc, policy)) reasons += QualificationReason.ACCURACY_TOO_LOW
            r
        }
        val firstFixRatio = if (firstFix == null) 0.0 else {
            val r = linear(firstFix.toDouble(), policy.firstFixFullMs.toDouble(), policy.firstFixZeroMs.toDouble())
            if (firstFix >= policy.firstFixZeroMs) reasons += QualificationReason.SLOW_FIRST_FIX
            r
        }
        val stabilityRatio = if (displacement == null) 0.0 else {
            val r = linear(displacement, policy.displacementFullM, policy.displacementZeroM) * sufficiency
            if (displacement >= policy.displacementZeroM) reasons += QualificationReason.UNSTABLE_POSITION
            r
        }
        val timestampRatio = timestampRatio(valid, input.nowMs, policy, reasons)
        val integrityRatio = when {
            input.integrity.spoofingFlagged || input.integrity.rootOrHookingIndicators -> 0.0
            input.integrity.appIntegrity == AppIntegrity.PASS -> 1.0
            input.integrity.appIntegrity == AppIntegrity.UNAVAILABLE -> 0.5
            else -> 0.0
        }

        val w = policy.weights
        val accuracyPts = w.accuracy * accuracyRatio * sufficiency
        val firstFixPts = w.firstFix * firstFixRatio
        val stabilityPts = w.stability * stabilityRatio
        val timestampPts = w.timestamps * timestampRatio
        val integrityPts = w.integrity * integrityRatio
        val total = (accuracyPts + firstFixPts + stabilityPts + timestampPts + integrityPts)
            .roundToInt().coerceIn(0, 100)

        val accuracyGateFailed = medianAcc == null || p90Acc == null || accuracyBeyondLimit(medianAcc, p90Acc, policy)
        val hardGateFailed = !input.permissionGranted || !input.locationServicesEnabled ||
            input.integrity.spoofingFlagged || valid.size < policy.minSamples || accuracyGateFailed
        var category = when {
            hardGateFailed -> QualificationCategory.UNQUALIFIED
            total >= policy.qualifiedMin -> QualificationCategory.QUALIFIED
            total >= policy.conditionalMin -> QualificationCategory.CONDITIONAL
            else -> QualificationCategory.UNQUALIFIED
        }
        val integrityUnavailable = input.integrity.appIntegrity == AppIntegrity.UNAVAILABLE
        if (integrityUnavailable && category == QualificationCategory.QUALIFIED) {
            category = QualificationCategory.CONDITIONAL
        }

        val status = when {
            !input.permissionGranted || !input.locationServicesEnabled -> LocationStatus.PERMISSION_DENIED
            input.integrity.spoofingFlagged -> LocationStatus.SPOOFING_DETECTED
            input.integrity.rootOrHookingIndicators ||
                input.integrity.appIntegrity == AppIntegrity.FAIL -> LocationStatus.SUSPICIOUS
            valid.size < policy.minSamples || accuracyGateFailed -> LocationStatus.LOW_ACCURACY
            integrityUnavailable -> LocationStatus.INTEGRITY_UNAVAILABLE
            category == QualificationCategory.UNQUALIFIED -> LocationStatus.DEVICE_UNQUALIFIED
            else -> LocationStatus.TRUSTED
        }

        return QualificationReport(
            policyVersion = policy.version,
            accuracyPoints = accuracyPts,
            firstFixPoints = firstFixPts,
            stabilityPoints = stabilityPts,
            timestampPoints = timestampPts,
            integrityPoints = integrityPts,
            total = total,
            category = category,
            status = status,
            reasons = reasons.toList(),
            metrics = QualificationMetrics(
                totalSamples = input.samples.size,
                validSamples = valid.size,
                medianAccuracyM = medianAcc,
                p90AccuracyM = p90Acc,
                firstFixMs = firstFix,
                medianDisplacementM = displacement,
            ),
        )
    }

    /** Akurasi di luar batas nol kebijakan (median atau P90) adalah hard gate, bukan sekadar skor rendah. */
    private fun accuracyBeyondLimit(median: Double, p90: Double, policy: QualificationPolicy) =
        median >= policy.medianAccuracyZeroM || p90 >= policy.p90AccuracyZeroM

    private fun isValid(s: LocationSample) =
        s.latitude.isFinite() && s.longitude.isFinite() && s.accuracyM.isFinite() &&
            s.latitude in -90.0..90.0 && s.longitude in -180.0..180.0 && s.accuracyM > 0.0

    /** Skor linear: 1 pada nilai <= full, 0 pada nilai >= zero. */
    internal fun linear(value: Double, full: Double, zero: Double): Double = when {
        value <= full -> 1.0
        value >= zero -> 0.0
        else -> (zero - value) / (zero - full)
    }

    internal fun median(values: List<Double>): Double? {
        if (values.isEmpty()) return null
        val s = values.sorted()
        val mid = s.size / 2
        return if (s.size % 2 == 1) s[mid] else (s[mid - 1] + s[mid]) / 2.0
    }

    /** Persentil nearest-rank. */
    internal fun percentile(values: List<Double>, p: Double): Double? {
        if (values.isEmpty()) return null
        val s = values.sorted()
        val rank = ceil(p * s.size).toInt().coerceIn(1, s.size)
        return s[rank - 1]
    }

    private fun medianDisplacement(valid: List<LocationSample>): Double? {
        if (valid.isEmpty()) return null
        val lat = median(valid.map { it.latitude })!!
        val lon = median(valid.map { it.longitude })!!
        return median(valid.map { GeoMath.distanceMeters(it.latitude, it.longitude, lat, lon) })
    }

    private fun timestampRatio(
        valid: List<LocationSample>,
        nowMs: Long,
        policy: QualificationPolicy,
        reasons: MutableSet<QualificationReason>,
    ): Double {
        if (valid.size < 2) return 0.0
        if (valid.any { it.timestampMs > nowMs + policy.maxFutureSkewMs }) {
            reasons += QualificationReason.FUTURE_TIMESTAMP
            return 0.0
        }
        var bad = 0
        for (i in 1 until valid.size) {
            val delta = valid[i].timestampMs - valid[i - 1].timestampMs
            if (delta < 0) {
                bad++
                reasons += QualificationReason.NON_MONOTONIC_TIMESTAMP
            } else if (delta > policy.maxSampleGapMs) {
                bad++
                reasons += QualificationReason.SAMPLE_GAP
            }
        }
        return 1.0 - bad.toDouble() / (valid.size - 1)
    }
}
