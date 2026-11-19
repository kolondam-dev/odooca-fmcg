package com.kolondam.odooca.field

import android.app.Application
import android.content.Context
import com.kolondam.odooca.field.data.db.OdoocaDatabase
import com.kolondam.odooca.field.data.network.ApiConfig
import com.kolondam.odooca.field.data.network.OdoocaApi
import com.kolondam.odooca.field.data.network.PersistentCookieJar
import com.kolondam.odooca.field.data.repo.OutboxRepository
import com.kolondam.odooca.field.data.repo.SessionManager
import com.kolondam.odooca.field.data.repo.SnapshotRepository
import com.kolondam.odooca.field.data.repo.VisitRepository
import com.kolondam.odooca.field.data.security.SessionStore
import com.kolondam.odooca.field.data.sync.OutboxServices

/** Kontainer dependensi manual: sedikit bagian bergerak, tanpa pemrosesan anotasi tambahan. */
class AppContainer(context: Context) {
    val config = ApiConfig(BuildConfig.BASE_URL, BuildConfig.DATABASE.ifBlank { null })
    val sessionStore = SessionStore(context)
    private val cookieJar = PersistentCookieJar(sessionStore)
    val api = OdoocaApi(config, cookieJar, sessionStore)
    val database: OdoocaDatabase = OdoocaDatabase.create(context)
    val session = SessionManager(api, sessionStore)
    val snapshots = SnapshotRepository(api, database)
    val outbox = OutboxRepository(database, api) { session.csrfToken }
    val visits = VisitRepository(database, outbox)
}

class OdoocaApplication : Application(), OutboxServices {
    lateinit var container: AppContainer
        private set

    override val outboxRepository: OutboxRepository get() = container.outbox

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
