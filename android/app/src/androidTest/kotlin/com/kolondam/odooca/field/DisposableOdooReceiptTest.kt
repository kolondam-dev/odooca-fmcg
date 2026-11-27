package com.kolondam.odooca.field

import android.os.Bundle
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.kolondam.odooca.field.data.repo.SessionAccess
import java.net.URI
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Opt-in, run on a fresh emulator against a committed disposable Odoo fixture. */
@RunWith(AndroidJUnit4::class)
class DisposableOdooReceiptTest {
    @Test
    fun submitOrReplay() {
        val arguments = InstrumentationRegistry.getArguments()
        assumeTrue(arguments.getString("dev02a") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val app = instrumentation.targetContext.applicationContext as OdoocaApplication
        val container = app.container
        val phase = arguments.getString("phase")
        require(phase == "first" || phase == "replay")
        val endpoint = URI(container.config.baseUrl)
        require(endpoint.scheme == "https" && endpoint.host != null)
        require(endpoint.userInfo == null && endpoint.rawQuery == null && endpoint.rawFragment == null)
        require(container.config.database?.startsWith("fmcg_staging_") == true)
        val uuid = requireNotNull(arguments.getString("uuid"))
        require(UUID.fromString(uuid).let { it.version() == 4 && it.toString() == uuid })
        val fixturePassword = requireNotNull(arguments.getString("fixturePassword"))

        runBlocking {
            val evidence = try {
                val identity = container.session.login("staging.capture.1", fixturePassword)
                val (_, snapshot) = container.api.snapshot()
                val scope = requireNotNull(snapshot.scope)
                assertEquals(identity.id, scope.userId)
                assertEquals(identity.companyId, scope.companyId)
                assertEquals(identity.businessDate, scope.businessDate)
                val version = if (phase == "first") {
                    snapshot.version
                } else {
                    // Wire payload must be identical even if the current catalog has a new version.
                    requireNotNull(arguments.getString("snapshotVersion"))
                }
                require(version.matches(Regex("odoo-read-v1:[a-f0-9]{64}")))
                val line = JSONObject().put("product_id", snapshot.products.single().id)
                    .put("qty", "1").put("uom", "carton")
                val payload = JSONObject().put("outlet_id", snapshot.outlets.single().id)
                    .put("snapshot_version", version).put("lines", JSONArray().put(line))
                val command = JSONObject().put("client_uuid", uuid)
                    .put("type", "sales.order.submit").put("payload", payload)
                val result = container.session.withOwner(identity.id) { lease ->
                    val csrf = requireNotNull(lease.csrfToken)
                    container.api.postCommand(command.toString(), csrf)
                }
                check(result is SessionAccess.Granted)
                val receipt = result.value
                assertEquals(uuid, receipt.clientUuid)
                check(receipt.status in setOf("accepted", "needs_approval") && receipt.reference.isNotBlank())
                JSONObject().put("phase", phase).put("request", command)
                    .put("user_id", scope.userId).put("company_id", scope.companyId)
                    .put("business_date", scope.businessDate)
                    .put("receipt", JSONObject().put("client_uuid", receipt.clientUuid)
                        .put("status", receipt.status).put("reference", receipt.reference))
            } finally {
                container.session.logout()
            }
            instrumentation.sendStatus(0, Bundle().apply { putString("dev02a_evidence", evidence.toString()) })
        }
    }
}
