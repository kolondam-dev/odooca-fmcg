package com.kolondam.odooca.field

import android.os.Bundle
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.kolondam.odooca.field.data.repo.OutboxRepository
import com.kolondam.odooca.field.data.repo.SessionManager
import com.kolondam.odooca.field.domain.sync.CommandState
import java.security.MessageDigest
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Opt-in against a fresh B09 fixture configured to truncate the first command receipt. */
@RunWith(AndroidJUnit4::class)
class OutboxRecoveryFixtureTest {
    @Test
    fun recoverReceipt() {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue(args.getString("dev03a") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val container = (context.applicationContext as OdoocaApplication).container
        check(container.config.baseUrl == "https://127.0.0.1:18443")
        check(container.config.database?.startsWith("fmcg_staging_") == true)
        val uuid = requireNotNull(args.getString("uuid"))
        check(UUID.fromString(uuid).let { it.version() == 4 && it.toString() == uuid })
        val phase = requireNotNull(args.getString("phase"))
        val session = SessionManager(container.api, container.sessionStore)
        val outbox = OutboxRepository(container.database, container.api, session)
        val dao = container.database.outbox()

        val evidence = runBlocking {
            when (phase) {
                "first" -> {
                    check(session.ownerId == null && dao.get(uuid) == null)
                    val owner = session.login("staging.capture.1", requireNotNull(args.getString("fixturePassword"))).id
                    check(dao.all(owner).isEmpty())
                    val (_, snapshot) = container.api.snapshot()
                    check(snapshot.scope?.userId == owner)
                    val line = JSONObject().put("product_id", snapshot.products.single().id)
                        .put("qty", "1").put("uom", "carton")
                    val payload = JSONObject().put("outlet_id", snapshot.outlets.single().id)
                        .put("snapshot_version", snapshot.version).put("lines", JSONArray().put(line))
                    val wire = JSONObject().put("client_uuid", uuid)
                        .put("type", "sales.order.submit").put("payload", payload).toString()
                    outbox.enqueueCommand(owner, uuid, wire)
                    val result = outbox.flush(owner)
                    check(result.sent == 1 && result.retryLater && !result.authRequired)
                    val queued = requireNotNull(dao.get(uuid))
                    check(queued.state == CommandState.QUEUED.name && queued.attempts == 1)
                    check(queued.payload == wire && queued.receiptReference == null)
                    JSONObject().put("wire_sha256", digest(wire)).put("state", queued.state).put("attempts", 1)
                }
                "recover" -> {
                    val queued = requireNotNull(dao.get(uuid))
                    check(queued.ownerId == session.ownerId && queued.attempts == 1)
                    check(queued.state in setOf(CommandState.QUEUED.name, CommandState.SENDING.name))
                    check(queued.receiptReference == null)
                    // Advance at most to the persisted retry deadline. No payload or retry flag is rewritten.
                    val result = outbox.flush(queued.ownerId) { maxOf(System.currentTimeMillis(), queued.nextAttemptAtMs) }
                    check(result.sent == 1 && !result.retryLater && !result.authRequired)
                    val accepted = requireNotNull(dao.get(uuid))
                    check(accepted.state in setOf(CommandState.ACCEPTED.name, CommandState.NEEDS_APPROVAL.name))
                    check(accepted.attempts == 2 && accepted.payload == queued.payload)
                    val reference = requireNotNull(accepted.receiptReference).also {
                        check(it.matches(Regex("S[0-9]{1,16}")))
                    }
                    JSONObject().put("wire_sha256", digest(accepted.payload)).put("state", accepted.state)
                        .put("attempts", 2).put("reference", reference)
                }
                else -> error("Invalid recovery phase")
            }
        }
        evidence.put("phase", phase).put("client_uuid", uuid)
        instrumentation.sendStatus(0, Bundle().apply { putString("dev03a_evidence", evidence.toString()) })
    }

    private fun digest(value: String): String =
        MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
}
