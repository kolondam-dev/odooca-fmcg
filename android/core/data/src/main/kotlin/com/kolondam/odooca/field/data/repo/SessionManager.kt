package com.kolondam.odooca.field.data.repo

import com.kolondam.odooca.field.data.network.ApiException
import com.kolondam.odooca.field.data.network.ApiJson
import com.kolondam.odooca.field.data.network.IdentityDto
import com.kolondam.odooca.field.data.network.OdoocaApi
import com.kolondam.odooca.field.data.security.SessionStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class SessionLease(val ownerId: String, val generation: Long, val csrfToken: String?)

sealed interface SessionAccess<out T> {
    data class Granted<T>(val lease: SessionLease, val value: T) : SessionAccess<T>
    data object Denied : SessionAccess<Nothing>
}

interface SessionRequestGate {
    suspend fun <T> withOwner(ownerId: String, block: suspend (SessionLease) -> T): SessionAccess<T>
    suspend fun invalidate(lease: SessionLease)
}

/** Sesi pengguna: login, identitas, dan pemilik antrean. Logout tidak menghapus outbox. */
class SessionManager(
    private val api: OdoocaApi,
    private val store: SessionStore,
    private val onAuthenticated: suspend (String) -> Unit = {},
) : SessionRequestGate {
    private val _identity = MutableStateFlow(restore())
    val identity: StateFlow<IdentityDto?> = _identity.asStateFlow()
    private val requestMutex = Mutex()
    private var generation = 0L

    val ownerId: String? get() = _identity.value?.id
    val csrfToken: String? get() = store.csrfToken
    val serverClockOffsetMs: Long get() = store.serverClockOffsetMs

    private fun restore(): IdentityDto? = store.identityJson?.let {
        runCatching { ApiJson.decodeFromString(IdentityDto.serializer(), it) }.getOrNull()
    }

    suspend fun login(login: String, password: String): IdentityDto = requestMutex.withLock {
        clearLocked()
        api.login(login.trim(), password)
        refreshIdentityLocked()
    }

    /** Mengambil identitas dari server; sesi yang sudah tidak valid (401) dibersihkan. */
    suspend fun refreshIdentity(): IdentityDto = requestMutex.withLock { refreshIdentityLocked() }

    private suspend fun refreshIdentityLocked(): IdentityDto {
        try {
            val identity = try {
                api.bootstrap()
            } catch (e: ApiException) {
                if (e.status !in listOf(403, 422)) throw e
                try {
                    api.attendanceIdentity()
                } catch (_: ApiException) {
                    throw e
                }
            }
            store.identityJson = ApiJson.encodeToString(IdentityDto.serializer(), identity)
            store.csrfToken = identity.csrfToken
            _identity.value = identity
            generation++
            if ("attendance.approval_only" !in identity.capabilities) onAuthenticated(identity.id)
            return identity
        } catch (e: ApiException) {
            if (e.status == 401) clearLocked()
            throw e
        }
    }

    suspend fun logout() = requestMutex.withLock { clearLocked() }

    override suspend fun <T> withOwner(
        ownerId: String,
        block: suspend (SessionLease) -> T,
    ): SessionAccess<T> = requestMutex.withLock {
        val current = _identity.value ?: return@withLock SessionAccess.Denied
        if (current.id != ownerId) return@withLock SessionAccess.Denied
        val lease = SessionLease(current.id, generation, store.csrfToken)
        SessionAccess.Granted(lease, block(lease))
    }

    override suspend fun invalidate(lease: SessionLease) = requestMutex.withLock {
        val current = _identity.value
        if (current?.id == lease.ownerId && generation == lease.generation) clearLocked()
    }

    private fun clearLocked() {
        api.clearSession()
        _identity.value = null
        generation++
    }
}
