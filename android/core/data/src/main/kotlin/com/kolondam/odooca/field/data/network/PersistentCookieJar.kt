package com.kolondam.odooca.field.data.network

import com.kolondam.odooca.field.data.security.SessionStore
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl

@Serializable
private data class StoredCookie(
    val name: String,
    val value: String,
    val expiresAt: Long,
    val domain: String,
    val path: String,
    val secure: Boolean,
    val httpOnly: Boolean,
    val hostOnly: Boolean,
)

/** Cookie jar yang menyimpan sesi Odoo terenkripsi, sehingga sesi bertahan setelah aplikasi ditutup. */
class PersistentCookieJar(private val store: SessionStore) : CookieJar {
    private val lock = Any()
    private var cookies: MutableList<Cookie> = load()

    private fun load(): MutableList<Cookie> {
        val raw = store.cookiesJson ?: return mutableListOf()
        return runCatching {
            ApiJson.decodeFromString(ListSerializer(StoredCookie.serializer()), raw).map {
                val b = Cookie.Builder().name(it.name).value(it.value).expiresAt(it.expiresAt).path(it.path)
                if (it.hostOnly) b.hostOnlyDomain(it.domain) else b.domain(it.domain)
                if (it.secure) b.secure()
                if (it.httpOnly) b.httpOnly()
                b.build()
            }.toMutableList()
        }.getOrDefault(mutableListOf())
    }

    private fun persist() {
        val stored = cookies.map {
            StoredCookie(it.name, it.value, it.expiresAt, it.domain, it.path, it.secure, it.httpOnly, it.hostOnly)
        }
        store.cookiesJson = ApiJson.encodeToString(ListSerializer(StoredCookie.serializer()), stored)
    }

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        synchronized(lock) {
            for (incoming in cookies) {
                this.cookies.removeAll { it.name == incoming.name && it.domain == incoming.domain && it.path == incoming.path }
                if (incoming.expiresAt > System.currentTimeMillis()) this.cookies.add(incoming)
            }
            persist()
        }
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> = synchronized(lock) {
        val now = System.currentTimeMillis()
        cookies.removeAll { it.expiresAt <= now }
        cookies.filter { it.matches(url) }
    }

    fun clear() = synchronized(lock) {
        cookies.clear()
        store.cookiesJson = null
    }
}
