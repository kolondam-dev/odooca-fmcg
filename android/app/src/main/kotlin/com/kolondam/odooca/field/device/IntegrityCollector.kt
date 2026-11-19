package com.kolondam.odooca.field.device

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.kolondam.odooca.field.domain.location.AppIntegrity
import com.kolondam.odooca.field.domain.location.IntegritySignals
import java.io.File

/**
 * Sinyal integritas perangkat yang dapat dikumpulkan secara lokal.
 *
 * Catatan jujur: verifikasi integritas aplikasi (Play Integrity atau pengganti) belum
 * diintegrasikan, jadi `appIntegrity` dilaporkan UNAVAILABLE dan hasil kualifikasi dibatasi
 * pada kategori bersyarat. Indikator root di sini hanya heuristik dan mudah dihindari;
 * keputusan risiko tetap ada di backend.
 */
class IntegrityCollector(private val context: Context) {
    fun collect(spoofingFlagged: Boolean): IntegritySignals = IntegritySignals(
        spoofingFlagged = spoofingFlagged,
        developerOptionsEnabled = developerOptionsEnabled(),
        rootOrHookingIndicators = rootIndicators(),
        appIntegrity = AppIntegrity.UNAVAILABLE,
    )

    private fun developerOptionsEnabled(): Boolean? = runCatching {
        Settings.Global.getInt(context.contentResolver, Settings.Global.DEVELOPMENT_SETTINGS_ENABLED, 0) == 1
    }.getOrNull()

    private fun rootIndicators(): Boolean {
        val suPaths = listOf(
            "/system/bin/su", "/system/xbin/su", "/sbin/su", "/system/sd/xbin/su",
            "/system/app/Superuser.apk", "/data/local/xbin/su", "/data/local/bin/su",
        )
        return Build.TAGS?.contains("test-keys") == true || suPaths.any { File(it).exists() }
    }
}
