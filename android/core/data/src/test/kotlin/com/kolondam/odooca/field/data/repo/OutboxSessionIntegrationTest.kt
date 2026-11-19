package com.kolondam.odooca.field.data.repo

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kolondam.odooca.field.data.db.OdoocaDatabase
import com.kolondam.odooca.field.data.network.ApiConfig
import com.kolondam.odooca.field.data.network.OdoocaApi
import com.kolondam.odooca.field.data.network.PersistentCookieJar
import com.kolondam.odooca.field.data.security.SecretCipher
import com.kolondam.odooca.field.data.security.SessionStore
import com.kolondam.odooca.field.domain.sync.CommandState
import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.runBlocking
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Eksekusi nyata lapisan repository + Room + sesi:
 * - antrean pemilik A tidak boleh memakai cookie/CSRF pemilik B,
 * - 401 menghentikan batch tepat setelah satu request,
 * - login ulang pemilik yang sama mengembalikan item ke antrean dengan UUID yang sama,
 * - pergantian akun tidak boleh menyela request yang sedang berjalan.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class OutboxSessionIntegrationTest {
    private lateinit var backend: SessionBackend
    private lateinit var database: OdoocaDatabase
    private lateinit var api: OdoocaApi
    private lateinit var session: SessionManager
    private lateinit var repository: OutboxRepository
    private lateinit var activeOutbox: OutboxRepository

    @BeforeTest
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        context.getSharedPreferences("odooca_session", Context.MODE_PRIVATE).edit().clear().commit()
        backend = SessionBackend()
        val baseUrl = backend.start()
        val store = SessionStore(context, PlainCipher)
        api = OdoocaApi(
            ApiConfig(baseUrl, null),
            PersistentCookieJar(store),
            store,
        )
        database = Room.inMemoryDatabaseBuilder(context, OdoocaDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        session = SessionManager(api, store) { ownerId -> activeOutbox.resumeAfterAuthentication(ownerId) }
        activeOutbox = OutboxRepository(database, api, session)
        repository = activeOutbox
    }

    @AfterTest
    fun tearDown() {
        database.close()
        backend.stop()
    }

    @Test
    fun queuedOwnerCannotUseAnotherOwnersSession(): Unit = runBlocking {
        session.login("A", "pw")
        enqueue("A", "a-1", 1)
        session.login("B", "pw")

        val blocked = repository.flush("A")

        assertTrue(blocked.authRequired)
        assertEquals(0, blocked.sent)
        assertTrue(backend.snapshot().isEmpty())
        assertEquals(CommandState.QUEUED.name, entity("a-1").state)

        session.login("A", "pw")
        val sent = repository.flush("A")

        assertEquals(1, sent.sent)
        assertEquals(listOf(CommandRequest("a-1", "A", "csrf-A")), backend.snapshot())
    }

    @Test
    fun first401StopsBatchAndOnlySameOwnerReauthenticationResumesIt(): Unit = runBlocking {
        session.login("A", "pw")
        enqueue("A", "a-1", 1)
        enqueue("A", "a-2", 2)
        backend.rejectNextCommand.set(true)

        val rejected = repository.flush("A")

        assertEquals(1, rejected.sent)
        assertTrue(rejected.authRequired)
        assertEquals(listOf("a-1"), backend.snapshot().map { it.uuid })
        assertEquals(CommandState.AUTH_REQUIRED.name, entity("a-1").state)
        assertEquals(CommandState.QUEUED.name, entity("a-2").state)
        assertNull(session.ownerId)

        session.login("B", "pw")
        assertEquals(CommandState.AUTH_REQUIRED.name, entity("a-1").state)
        assertTrue(repository.flush("A").authRequired)
        assertEquals(1, backend.snapshot().size)

        session.login("A", "pw")
        assertEquals(CommandState.QUEUED.name, entity("a-1").state)
        val resumed = repository.flush("A")

        assertEquals(2, resumed.sent)
        assertFalse(resumed.authRequired)
        assertEquals(listOf("a-1", "a-1", "a-2"), backend.snapshot().map { it.uuid })
        assertTrue(backend.snapshot().all { it.sessionOwner == "A" && it.csrf == "csrf-A" })
        assertEquals(CommandState.ACCEPTED.name, entity("a-1").state)
        assertEquals(CommandState.ACCEPTED.name, entity("a-2").state)
    }

    @Test
    fun accountSwitchBetweenTwoSendsStopsBeforeSecondRequest(): Unit = runBlocking {
        repository = OutboxRepository(database, api, SwitchingGate(session, "B"))
        activeOutbox = repository
        session.login("A", "pw")
        enqueue("A", "a-1", 1)
        enqueue("A", "a-2", 2)

        val result = repository.flush("A")

        assertEquals(1, result.sent)
        assertTrue(result.authRequired)
        assertEquals("B", session.ownerId)
        assertEquals(listOf("a-1"), backend.snapshot().map { it.uuid })
        assertEquals("A", backend.snapshot().single().sessionOwner)
        assertEquals(CommandState.ACCEPTED.name, entity("a-1").state)
        assertEquals(CommandState.QUEUED.name, entity("a-2").state)

        session.login("A", "pw")
        assertEquals(1, repository.flush("A").sent)
        assertEquals(listOf("a-1", "a-2"), backend.snapshot().map { it.uuid })
        assertTrue(backend.snapshot().all { it.sessionOwner == "A" && it.csrf == "csrf-A" })
    }

    private suspend fun enqueue(owner: String, id: String, createdAt: Long) {
        repository.enqueueCommand(owner, id, "{\"client_uuid\":\"$id\"}", nowMs = createdAt)
    }

    private suspend fun entity(id: String) = requireNotNull(database.outbox().get(id))

    private data class CommandRequest(val uuid: String, val sessionOwner: String?, val csrf: String?)

    /**
     * Menjalankan pergantian akun tepat di antara dua pengiriman, sehingga urutannya deterministik:
     * item pertama selesai dengan sesi A, lalu login B menunggu sampai lease dilepas.
     */
    private class SwitchingGate(
        private val session: SessionManager,
        private val nextOwner: String,
    ) : SessionRequestGate {
        private val switched = AtomicBoolean(false)

        override suspend fun <T> withOwner(
            ownerId: String,
            block: suspend (SessionLease) -> T,
        ): SessionAccess<T> {
            if (!switched.compareAndSet(false, true)) return session.withOwner(ownerId, block)

            val loginStarted = CountDownLatch(1)
            val loginDone = AtomicBoolean(false)
            var loginThread: Thread? = null
            val result = session.withOwner(ownerId) { lease ->
                loginThread = thread(isDaemon = true, name = "session-switch") {
                    loginStarted.countDown()
                    runBlocking { session.login(nextOwner, "pw") }
                    loginDone.set(true)
                }
                check(loginStarted.await(5, TimeUnit.SECONDS)) { "login thread did not start" }
                Thread.sleep(150)
                val value = block(lease)
                assertFalse(
                    loginDone.get(),
                    "login must not replace the session while a send holds the lease",
                )
                value
            }
            val thread = checkNotNull(loginThread) { "login thread was not started" }
            thread.join(5_000)
            check(!thread.isAlive) { "login did not finish" }
            check(loginDone.get()) { "login did not complete" }
            return result
        }

        override suspend fun invalidate(lease: SessionLease) = session.invalidate(lease)
    }

    /** Server HTTP JDK minimal: login sesi, bootstrap identitas, dan penerimaan command. */
    private class SessionBackend {
        private val commands = ConcurrentLinkedQueue<CommandRequest>()
        private val executor = Executors.newFixedThreadPool(4)
        private lateinit var server: HttpServer
        val rejectNextCommand = AtomicBoolean(false)

        fun start(): String {
            server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
            server.executor = executor
            server.createContext("/") { exchange -> respond(exchange) }
            server.start()
            return "http://127.0.0.1:${server.address.port}"
        }

        fun stop() {
            server.stop(0)
            executor.shutdownNow()
        }

        fun snapshot(): List<CommandRequest> = commands.toList()

        private fun respond(exchange: HttpExchange) {
            try {
                val body = exchange.requestBody.readBytes().toString(Charsets.UTF_8)
                val cookie = exchange.requestHeaders.getFirst("Cookie")
                when (exchange.requestURI.path) {
                    "/web/session/authenticate" -> {
                        val login = Regex("\"login\":\"([^\"]+)\"").find(body)?.groupValues?.get(1)
                        if (login == null) {
                            write(exchange, 400, "{}", null)
                        } else {
                            write(
                                exchange,
                                200,
                                "{\"jsonrpc\":\"2.0\",\"result\":{\"uid\":1}}",
                                "session_id=$login; Path=/",
                            )
                        }
                    }
                    "/api/v1/me/bootstrap" -> {
                        val owner = ownerOf(cookie)
                        if (owner == null) {
                            write(exchange, 401, "{}", null)
                        } else {
                            write(
                                exchange,
                                200,
                                "{\"id\":\"$owner\",\"companyId\":\"1\",\"name\":\"User $owner\"," +
                                    "\"businessDate\":\"2026-11-19\",\"csrfToken\":\"csrf-$owner\"}",
                                null,
                            )
                        }
                    }
                    "/api/v1/sync/commands" -> {
                        val uuid = Regex("\"client_uuid\":\"([^\"]+)\"")
                            .find(body)
                            ?.groupValues
                            ?.get(1)
                            ?: "missing"
                        commands += CommandRequest(
                            uuid,
                            ownerOf(cookie),
                            exchange.requestHeaders.getFirst("X-CSRF-Token"),
                        )
                        if (rejectNextCommand.compareAndSet(true, false)) {
                            write(exchange, 401, "{}", null)
                        } else {
                            write(
                                exchange,
                                200,
                                "{\"client_uuid\":\"$uuid\",\"status\":\"accepted\"," +
                                    "\"reference\":\"R-$uuid\"}",
                                null,
                            )
                        }
                    }
                    else -> write(exchange, 404, "{}", null)
                }
            } catch (t: Throwable) {
                runCatching { write(exchange, 500, "{}", null) }
            } finally {
                runCatching { exchange.close() }
            }
        }

        private fun write(exchange: HttpExchange, code: Int, body: String, cookie: String?) {
            val bytes = body.toByteArray(Charsets.UTF_8)
            exchange.responseHeaders.set("Content-Type", "application/json")
            if (cookie != null) exchange.responseHeaders.add("Set-Cookie", cookie)
            exchange.sendResponseHeaders(code, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }

        private fun ownerOf(cookie: String?): String? = cookie
            ?.split(';')
            ?.map { it.trim() }
            ?.firstOrNull { it.startsWith("session_id=") }
            ?.substringAfter('=')
            ?.takeIf { it.isNotBlank() }
    }

    private object PlainCipher : SecretCipher {
        override fun encrypt(plain: String): String = "plain:$plain"
        override fun decrypt(token: String): String? = token.removePrefix("plain:")
    }
}
