package com.kolondam.odooca.field

import android.content.Context
import android.os.Bundle
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.kolondam.odooca.field.data.network.ApiException
import com.kolondam.odooca.field.data.repo.OutboxRepository
import com.kolondam.odooca.field.data.repo.SessionManager
import com.kolondam.odooca.field.data.security.SessionStore
import com.kolondam.odooca.field.domain.sync.CommandState
import java.security.KeyStore
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeviceFixtureSessionTest {
    @Test
    fun recordDeviceSessionEvidence() {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue(args.getString("dev02b") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        check(context.packageName == "com.kolondam.odooca.field.fixture")
        val container = (context.applicationContext as OdoocaApplication).container
        if (BuildConfig.DEVICE_SYSTEM_TLS) {
            check(container.config.baseUrl.startsWith("https://") && !container.config.database.isNullOrBlank())
        } else {
            check(container.config.baseUrl == "https://127.0.0.1:18443")
            check(container.config.database?.startsWith("fmcg_staging_") == true)
        }
        val phase = requireNotNull(args.getString("phase"))
        val prefs = context.getSharedPreferences("dev02b_idle", Context.MODE_PRIVATE)
        val session = SessionManager(container.api, container.sessionStore) { owner ->
            container.outbox.resumeAfterAuthentication(owner)
        } // This session does not schedule a background flush.

        val outbox = OutboxRepository(container.database, container.api, session)

        suspend fun login(account: String): String {
            val alias = args.getString("login$account") ?: if (BuildConfig.DEVICE_SYSTEM_TLS) {
                error("Approved TEST login is required")
            } else if (account == "A") {
                "staging.capture.1"
            } else {
                "staging.capture.2"
            }
            check(alias.isNotBlank())
            return session.login(alias, requireNotNull(args.getString("password$account"))).id
        }

        runBlocking {
            when (phase) {
                "preflight" -> {
                    check(session.ownerId == null)
                    session.logout()
                    try {
                        expectUnauthorized { container.api.bootstrap() }
                        expectUnauthorized { container.api.snapshot() }
                    } finally {
                        session.logout()
                    }
                    verifyCleared(context)
                }
                "isolation" -> {
                    check(container.session.ownerId == null) { "Logout from the fixture UI before isolation" }
                    val owner = login("A")
                    val (_, snapshotA) = container.api.snapshot()
                    check(snapshotA.scope?.userId == owner)
                    verifyKeystore(context)
                    val id = UUID.randomUUID().toString()
                    // No valid business command. Only the owner/lease and retained UUID are under test.
                    outbox.enqueueCommand(owner, id, """{"client_uuid":"$id","type":"dev02b.local"}""")
                    session.logout()
                    verifyCleared(context)
                    val other = login("B")
                    val (_, snapshotB) = container.api.snapshot()
                    check(other != owner && snapshotB.scope?.userId == other)
                    val outletsA = snapshotA.outlets.map { it.id }.toSet()
                    val outletsB = snapshotB.outlets.map { it.id }.toSet()
                    check(outletsA.isNotEmpty() && outletsB.isNotEmpty() && outletsA != outletsB)
                    val wrongOwner = outbox.flush(owner)
                    check(wrongOwner.authRequired && wrongOwner.sent == 0)
                    val dao = container.database.outbox()
                    check(dao.all(other).none { it.id == id })
                    val row = requireNotNull(dao.get(id))
                    check(row.ownerId == owner && row.state == CommandState.QUEUED.name && row.attempts == 0)
                    dao.update(row.copy(state = CommandState.AUTH_REQUIRED.name))
                    check(login("A") == owner)
                    val restored = requireNotNull(dao.get(id))
                    check(restored.state == CommandState.QUEUED.name)
                    dao.update(restored.copy(state = CommandState.DRAFT.name))
                    session.logout()
                    verifyCleared(context)
                }
                "idle_begin" -> {
                    val ttl = requireNotNull(args.getString("idleSeconds")).toInt()
                    require(ttl in 15..600)
                    login("A")
                    verifyKeystore(context)
                    check(prefs.edit().putLong("since", SystemClock.elapsedRealtime()).putInt("seconds", ttl).commit())
                }
                "idle_end" -> {
                    val since = prefs.getLong("since", -1)
                    val ttl = prefs.getInt("seconds", 0)
                    check(since >= 0 && ttl in 15..600 && SystemClock.elapsedRealtime() - since >= (ttl + 5) * 1000L)
                    check(session.ownerId != null)
                    verifyKeystore(context)
                    expectUnauthorized { session.refreshIdentity() }
                    check(session.ownerId == null)
                    verifyCleared(context)
                    check(prefs.edit().remove("since").remove("seconds").commit())
                }
                else -> error("Unknown fixture phase")
            }
        }
        instrumentation.sendStatus(0, Bundle().apply { putString("dev02b_result", "$phase=passed") })
    }

    private suspend fun expectUnauthorized(request: suspend () -> Unit) {
        try {
            request()
            error("Expected HTTP 401")
        } catch (failure: ApiException) {
            check(failure.status == 401) { "Expected HTTP 401, got ${failure.status}" }
        }
    }

    private fun verifyKeystore(context: Context) {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        check(keyStore.containsAlias("odooca_session_key"))
        val stored = SessionStore(context)
        val prefs = context.getSharedPreferences("odooca_session", Context.MODE_PRIVATE)
        for ((key, value) in listOf("cookies" to stored.cookiesJson, "csrf" to stored.csrfToken,
            "identity" to stored.identityJson)) {
            check(!value.isNullOrBlank())
            val ciphertext = prefs.getString(key, null)
            check(!ciphertext.isNullOrBlank() && ciphertext != value && !ciphertext.contains(value))
        }
    }

    private fun verifyCleared(context: Context) {
        val prefs = context.getSharedPreferences("odooca_session", Context.MODE_PRIVATE)
        check(listOf("cookies", "csrf", "identity").none(prefs::contains))
    }
}
