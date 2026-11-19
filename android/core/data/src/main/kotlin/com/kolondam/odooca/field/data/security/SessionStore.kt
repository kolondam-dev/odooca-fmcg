package com.kolondam.odooca.field.data.security

import android.content.Context

/**
 * Penyimpanan sesi di perangkat: cookie sesi, token CSRF, dan identitas terakhir.
 * Nilai rahasia dienkripsi dengan Keystore; tidak ikut backup.
 */
class SessionStore(context: Context, private val cipher: SecretCipher = KeystoreCipher()) {
    private val prefs = context.getSharedPreferences("odooca_session", Context.MODE_PRIVATE)

    private fun putSecret(key: String, value: String?) {
        prefs.edit().apply {
            if (value == null) remove(key) else putString(key, cipher.encrypt(value))
        }.apply()
    }

    private fun getSecret(key: String): String? = prefs.getString(key, null)?.let(cipher::decrypt)

    var cookiesJson: String?
        get() = getSecret(KEY_COOKIES)
        set(value) = putSecret(KEY_COOKIES, value)

    var csrfToken: String?
        get() = getSecret(KEY_CSRF)
        set(value) = putSecret(KEY_CSRF, value)

    var identityJson: String?
        get() = getSecret(KEY_IDENTITY)
        set(value) = putSecret(KEY_IDENTITY, value)

    /** Selisih jam server terhadap jam perangkat (ms), dari header Date respons. */
    var serverClockOffsetMs: Long
        get() = prefs.getLong(KEY_CLOCK, 0L)
        set(value) = prefs.edit().putLong(KEY_CLOCK, value).apply()

    /** Hapus kredensial sesi. Antrean outbox milik pemilik tidak disentuh. */
    fun clearSession() {
        prefs.edit().remove(KEY_COOKIES).remove(KEY_CSRF).remove(KEY_IDENTITY).apply()
    }

    private companion object {
        const val KEY_COOKIES = "cookies"
        const val KEY_CSRF = "csrf"
        const val KEY_IDENTITY = "identity"
        const val KEY_CLOCK = "clock_offset_ms"
    }
}
