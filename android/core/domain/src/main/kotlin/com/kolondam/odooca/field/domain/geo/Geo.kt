package com.kolondam.odooca.field.domain.geo

import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Jarak haversine. Rumus dan jari-jari bumi sama dengan server (`distance_m`)
 * dan klien web (`distanceMeters`) agar keputusan geofence konsisten.
 */
object GeoMath {
    const val EARTH_RADIUS_M = 6_371_000.0

    fun distanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val a = Math.toRadians(lat1)
        val b = Math.toRadians(lat2)
        val h = sin((b - a) / 2).pow(2) +
            cos(a) * cos(b) * sin(Math.toRadians(lon2 - lon1) / 2).pow(2)
        return EARTH_RADIUS_M * 2 * asin(sqrt(h.coerceIn(0.0, 1.0)))
    }
}

enum class GeofenceStatus { INSIDE, OUTSIDE, UNCERTAIN }

/**
 * Penilaian geofence di sisi klien. Server menolak bila jarak + akurasi >= radius,
 * jadi "dalam" di sini memakai batas ketat (<) agar klien tidak menyatakan layak
 * pada kasus yang pasti ditolak server tepat di batas. Server tetap berwenang.
 */
object Geofence {
    const val MIN_RADIUS_M = 5.0
    const val MAX_OUTLET_RADIUS_M = 150.0
    const val MAX_OFFICE_RADIUS_M = 500.0

    fun assess(
        distanceM: Double,
        accuracyM: Double,
        radiusM: Double,
        maxRadiusM: Double = MAX_OUTLET_RADIUS_M,
    ): GeofenceStatus {
        if (!distanceM.isFinite() || !accuracyM.isFinite() || !radiusM.isFinite() ||
            distanceM < 0 || accuracyM < 0 || radiusM < MIN_RADIUS_M || radiusM > maxRadiusM
        ) {
            return GeofenceStatus.UNCERTAIN
        }
        return when {
            distanceM + accuracyM < radiusM -> GeofenceStatus.INSIDE
            distanceM - accuracyM > radiusM -> GeofenceStatus.OUTSIDE
            else -> GeofenceStatus.UNCERTAIN
        }
    }
}
