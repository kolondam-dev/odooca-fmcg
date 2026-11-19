package com.kolondam.odooca.field.domain.geo

enum class TimingStatus {
    OK,
    FIX_FUTURE, FIX_STALE,
    PHOTO_FUTURE, PHOTO_STALE,
    DEVICE_FUTURE, DEVICE_STALE,
    PHOTO_AFTER_DEVICE_RECORD,
}

/**
 * Jendela kesegaran bukti yang diterapkan server saat menerima foto + lokasi:
 * fix lokasi -1..60 detik, pemilihan foto -5..300 detik, catatan perangkat -5..60 detik,
 * dan foto tidak boleh dipilih setelah catatan perangkat dibuat.
 * Semua waktu dalam epoch milidetik; `nowMs` sebaiknya sudah dikoreksi selisih jam server.
 */
object EvidenceTiming {
    const val FIX_MAX_AGE_MS = 60_000L
    const val FIX_MAX_AHEAD_MS = 1_000L
    const val PHOTO_MAX_AGE_MS = 300_000L
    const val PHOTO_MAX_AHEAD_MS = 5_000L
    const val DEVICE_MAX_AGE_MS = 60_000L
    const val DEVICE_MAX_AHEAD_MS = 5_000L

    fun assess(
        nowMs: Long,
        fixSampledAtMs: Long,
        photoSelectedAtMs: Long,
        deviceRecordedAtMs: Long,
    ): TimingStatus {
        val fixAge = nowMs - fixSampledAtMs
        if (fixAge < -FIX_MAX_AHEAD_MS) return TimingStatus.FIX_FUTURE
        if (fixAge > FIX_MAX_AGE_MS) return TimingStatus.FIX_STALE
        val photoAge = nowMs - photoSelectedAtMs
        if (photoAge < -PHOTO_MAX_AHEAD_MS) return TimingStatus.PHOTO_FUTURE
        if (photoAge > PHOTO_MAX_AGE_MS) return TimingStatus.PHOTO_STALE
        val deviceAge = nowMs - deviceRecordedAtMs
        if (deviceAge < -DEVICE_MAX_AHEAD_MS) return TimingStatus.DEVICE_FUTURE
        if (deviceAge > DEVICE_MAX_AGE_MS) return TimingStatus.DEVICE_STALE
        if (photoSelectedAtMs > deviceRecordedAtMs) return TimingStatus.PHOTO_AFTER_DEVICE_RECORD
        return TimingStatus.OK
    }
}
