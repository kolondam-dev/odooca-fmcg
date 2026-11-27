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
        check(container.config.baseUrl == "https://127.0.0.1:18443")
        check(container.config.database?.startsWith("fmcg_staging_") == true)
        val phase = requireNotNull(args.getString("phase"))
        val prefs = context.getSharedPreferences("dev02b_idle", Context.MODE_PRIVATE)
        val session = SessionManager(container.api, container.sessionStore) { owner ->
            container.outbox.resumeAfterAuthentication(owner)
        } // This session does not schedule a background flush.

        val outbox = OutboxRepository(container.database, container.api, session)

        runBlocking {
            when (phase) {
                "isolation" -> {
                    check(container.session.ownerId == null) { "Logout from the fixture UI before isolation" }
                    val owner = session.login("staging.capture.1", requireNotNull(args.getString("passwordA"))).id
                    container.api.snapshot()
                    verifyKeystore(context)
                    val id = UUID.randomUUID().toString()
                    // No valid business command. Only the owner/lease and retained UUID are under test.
                    outbox.enqueueCommand(owner, id, """{"client_uuid":"$id","type":"dev02b.local"}""")
                    session.logout()
                    verifyCleared(context)
                    val other = session.login("staging.capture.2", requireNotNull(args.getString("passwordB"))).id
                    check(other != owner)
                    val wrongOwner = outbox.flush(owner)
                    check(wrongOwner.authRequired && wrongOwner.sent == 0)
                    val dao = container.database.outbox()
                    check(dao.all(other).none { it.id == id })
                    val row = requireNotNull(dao.get(id))
                    check(row.ownerId == owner && row.state == CommandState.QUEUED.name && row.attempts == 0)
                    dao.update(row.copy(state = CommandState.AUTH_REQUIRED.name))
                    check(session.login("staging.capture.1", requireNotNull(args.getString("passwordA"))).id == owner)
                    val restored = requireNotNull(dao.get(id))
                    check(restored.state == CommandState.QUEUED.name)
                    dao.update(restored.copy(state = CommandState.DRAFT.name))
                    session.logout()
                    verifyCleared(context)
                }
                "idle_begin" -> {
                    val ttl = requireNotNull(args.getString("idleSeconds")).toInt()
                    require(ttl in 15..600)
                    session.login("staging.capture.1", requireNotNull(args.getString("passwordA")))
                    verifyKeystore(context)
                    check(prefs.edit().putLong("since", SystemClock.elapsedRealtime()).putInt("seconds", ttl).commit())
                }
                "idle_end" -> {
                    val since = prefs.getLong("since", -1)
                    val ttl = prefs.getInt("seconds", 0)
                    check(since >= 0 && ttl in 15..600 && SystemClock.elapsedRealtime() - since >= (ttl + 5) * 1000L)
                    check(session.ownerId != null)
                    verifyKeystore(context)
                    try {
                        session.refreshIdentity()
                        error("Expired fixture cookie was accepted")
                    } catch (failure: ApiException) {
                        check(failure.status == 401)
                    }
                    check(session.ownerId == null)
                    verifyCleared(context)
                    check(prefs.edit().remove("since").remove("seconds").commit())
                }
                else -> error("Unknown fixture phase")
            }
        }
        instrumentation.sendStatus(0, Bundle().apply { putString("dev02b_result", "$phase=passed") })
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
