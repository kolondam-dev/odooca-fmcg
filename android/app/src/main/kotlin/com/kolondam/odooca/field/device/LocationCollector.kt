package com.kolondam.odooca.field.device

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.Looper
import androidx.core.content.ContextCompat
import com.kolondam.odooca.field.domain.location.LocationSample
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

/** Sampel lokasi beserta penanda dari sistem bahwa lokasi berasal dari provider buatan. */
data class CollectedFix(val sample: LocationSample, val flaggedBySystem: Boolean)

/**
 * Pengumpul lokasi memakai LocationManager platform (provider GPS), tanpa ketergantungan
 * Google Play Services, sehingga tetap bekerja di perangkat lama tanpa GMS.
 */
class LocationCollector(private val context: Context) {
    private val manager get() = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    fun gpsEnabled(): Boolean = runCatching { manager.isProviderEnabled(LocationManager.GPS_PROVIDER) }.getOrDefault(false)

    @SuppressLint("MissingPermission")
    fun fixes(): Flow<CollectedFix> = callbackFlow {
        val listener = object : LocationListener {
            override fun onLocationChanged(location: Location) {
                trySend(location.toFix())
            }

            // Wajib diimplementasikan pada Android di bawah API 29 (metode abstrak di sana).
            @Suppress("OVERRIDE_DEPRECATION", "DEPRECATION")
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
            override fun onProviderEnabled(provider: String) = Unit
            override fun onProviderDisabled(provider: String) = Unit
        }
        manager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1_000L, 0f, listener, Looper.getMainLooper())
        awaitClose { manager.removeUpdates(listener) }
    }

    private fun Location.toFix(): CollectedFix {
        val flagged = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            isMock
        } else {
            @Suppress("DEPRECATION")
            isFromMockProvider
        }
        return CollectedFix(
            sample = LocationSample(
                latitude = latitude,
                longitude = longitude,
                accuracyM = if (hasAccuracy()) accuracy.toDouble() else Double.NaN,
                timestampMs = time,
                provider = provider.orEmpty(),
            ),
            flaggedBySystem = flagged,
        )
    }
}
