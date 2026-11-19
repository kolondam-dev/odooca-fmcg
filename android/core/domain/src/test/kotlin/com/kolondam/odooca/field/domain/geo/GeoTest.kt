package com.kolondam.odooca.field.domain.geo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class GeoTest {
    @Test
    fun oneDegreeOfLatitudeIsAbout111Km() {
        val d = GeoMath.distanceMeters(0.0, 100.0, 1.0, 100.0)
        assertTrue(kotlin.math.abs(d - 111_194.9) < 1.0, "jarak=$d")
    }

    @Test
    fun samePointIsZero() {
        assertEquals(0.0, GeoMath.distanceMeters(1.4870, 124.8428, 1.4870, 124.8428), 1e-9)
    }

    @Test
    fun distanceIsSymmetric() {
        val a = GeoMath.distanceMeters(1.48, 124.84, 1.50, 124.90)
        val b = GeoMath.distanceMeters(1.50, 124.90, 1.48, 124.84)
        assertEquals(a, b, 1e-6)
    }

    @Test
    fun insideWhenDistancePlusAccuracyBelowRadius() {
        assertEquals(GeofenceStatus.INSIDE, Geofence.assess(10.0, 5.0, 50.0))
    }

    @Test
    fun exactBoundaryIsUncertainBecauseServerRejectsEquality() {
        assertEquals(GeofenceStatus.UNCERTAIN, Geofence.assess(49.0, 1.0, 50.0))
    }

    @Test
    fun outsideWhenDistanceMinusAccuracyExceedsRadius() {
        assertEquals(GeofenceStatus.OUTSIDE, Geofence.assess(100.0, 10.0, 50.0))
    }

    @Test
    fun uncertainWhenCircleOverlapsBoundary() {
        assertEquals(GeofenceStatus.UNCERTAIN, Geofence.assess(55.0, 10.0, 50.0))
    }

    @Test
    fun invalidInputsAreUncertain() {
        assertEquals(GeofenceStatus.UNCERTAIN, Geofence.assess(10.0, 5.0, 4.0))
        assertEquals(GeofenceStatus.UNCERTAIN, Geofence.assess(10.0, 5.0, 151.0))
        assertEquals(GeofenceStatus.UNCERTAIN, Geofence.assess(-1.0, 5.0, 50.0))
        assertEquals(GeofenceStatus.UNCERTAIN, Geofence.assess(10.0, -5.0, 50.0))
        assertEquals(GeofenceStatus.UNCERTAIN, Geofence.assess(Double.NaN, 5.0, 50.0))
    }

    @Test
    fun officeRadiusAllowsUpTo500() {
        assertEquals(
            GeofenceStatus.INSIDE,
            Geofence.assess(100.0, 10.0, 300.0, maxRadiusM = Geofence.MAX_OFFICE_RADIUS_M),
        )
        assertEquals(GeofenceStatus.UNCERTAIN, Geofence.assess(100.0, 10.0, 300.0))
    }
}

class EvidenceTimingTest {
    private val now = 10_000_000L

    private fun assess(fixAge: Long, photoAge: Long, deviceAge: Long) =
        EvidenceTiming.assess(now, now - fixAge, now - photoAge, now - deviceAge)

    @Test
    fun freshEvidenceIsOk() {
        assertEquals(TimingStatus.OK, assess(fixAge = 30_000, photoAge = 20_000, deviceAge = 10_000))
    }

    @Test
    fun fixBoundaryAt60Seconds() {
        assertEquals(TimingStatus.OK, assess(60_000, 20_000, 10_000))
        assertEquals(TimingStatus.FIX_STALE, assess(60_001, 20_000, 10_000))
    }

    @Test
    fun fixInTheFutureBeyondOneSecond() {
        assertEquals(TimingStatus.OK, assess(-1_000, 20_000, 10_000))
        assertEquals(TimingStatus.FIX_FUTURE, assess(-1_001, 20_000, 10_000))
    }

    @Test
    fun photoWindowIs300SecondsBack() {
        // foto dipilih 60 detik lalu, catatan perangkat 10 detik lalu: urutan benar
        assertEquals(TimingStatus.OK, assess(30_000, 60_000, 10_000))
        assertEquals(TimingStatus.PHOTO_STALE, assess(30_000, 300_001, 10_000))
        assertEquals(TimingStatus.PHOTO_FUTURE, assess(30_000, -5_001, 10_000))
    }

    @Test
    fun deviceRecordWindowIs60SecondsBack() {
        assertEquals(TimingStatus.DEVICE_STALE, assess(30_000, 20_000, 60_001))
        assertEquals(TimingStatus.DEVICE_FUTURE, assess(30_000, 20_000, -5_001))
    }

    @Test
    fun photoCannotBeSelectedAfterDeviceRecord() {
        // foto dipilih 10 detik lalu, tetapi catatan perangkat dibuat 20 detik lalu
        assertEquals(TimingStatus.PHOTO_AFTER_DEVICE_RECORD, assess(30_000, 10_000, 20_000))
    }
}
