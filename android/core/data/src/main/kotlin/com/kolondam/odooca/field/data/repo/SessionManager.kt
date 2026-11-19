package com.kolondam.odooca.field.data.repo

import com.kolondam.odooca.field.data.network.ApiException
import com.kolondam.odooca.field.data.network.ApiJson
import com.kolondam.odooca.field.data.network.IdentityDto
import com.kolondam.odooca.field.data.network.OdoocaApi
import com.kolondam.odooca.field.data.security.SessionStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Sesi pengguna: login, identitas, dan pemilik antrean. Logout tidak menghapus outbox. */
class SessionManager(private val api: OdoocaApi, private val store: SessionStore) {
    private val _identity = MutableStateFlow(restore())
    val identity: StateFlow<IdentityDto?> = _identity.asStateFlow()

    val ownerId: String? get() = _identity.value?.id
    val csrfToken: String? get() = store.csrfToken
    val serverClockOffsetMs: Long get() = store.serverClockOffsetMs

    private fun restore(): IdentityDto? = store.identityJson?.let {
        runCatching { ApiJson.decodeFromString(IdentityDto.serializer(), it) }.getOrNull()
    }

    suspend fun login(login: String, password: String): IdentityDto {
        api.login(login.trim(), password)
        return refreshIdentity()
    }

    /** Mengambil identitas dari server; sesi yang sudah tidak valid (401) dibersihkan. */
    suspend fun refreshIdentity(): IdentityDto {
        try {
            val identity = api.bootstrap()
            store.identityJson = ApiJson.encodeToString(IdentityDto.serializer(), identity)
            store.csrfToken = identity.csrfToken
            _identity.value = identity
            return identity
        } catch (e: ApiException) {
            if (e.status == 401) logout()
            throw e
        }
    }

    fun logout() {
        api.clearSession()
        _identity.value = null
    }
}
