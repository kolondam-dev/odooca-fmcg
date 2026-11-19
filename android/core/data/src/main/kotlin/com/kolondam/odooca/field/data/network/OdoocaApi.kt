package com.kolondam.odooca.field.data.network

import com.kolondam.odooca.field.data.security.SessionStore
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.io.File
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** Kegagalan API. `status` null berarti tidak ada respons (jaringan putus atau timeout). */
class ApiException(val status: Int?, message: String) : Exception(message)

/**
 * Klien ke backend Odoo yang nyata. Tidak ada jalur data pengganti: bila request gagal,
 * kegagalan dilaporkan apa adanya.
 */
class OdoocaApi(
    private val config: ApiConfig,
    private val jar: PersistentCookieJar,
    private val store: SessionStore,
) {
    private val client: OkHttpClient = OkHttpClient.Builder()
        .cookieJar(jar)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val response = chain.proceed(chain.request())
            response.headers.getDate("Date")?.let { store.serverClockOffsetMs = it.time - System.currentTimeMillis() }
            response
        }
        .build()

    private fun url(path: String): String {
        check(config.isConfigured) { "Alamat backend belum dikonfigurasi (properti Gradle odooca.baseUrl)." }
        return config.baseUrl + path
    }

    private suspend fun execute(request: Request): Pair<Int, String> = withContext(Dispatchers.IO) {
        try {
            client.newCall(request).execute().use { it.code to it.body?.string().orEmpty() }
        } catch (e: IOException) {
            throw ApiException(null, e.message ?: "Jaringan tidak tersedia")
        }
    }

    private fun failure(code: Int, body: String): ApiException =
        ApiException(code, "HTTP $code: ${body.take(200)}")

    /** Login sesi Odoo (cookie disimpan terenkripsi). Pengganti token native bila backend sudah menyediakannya. */
    suspend fun login(login: String, password: String) {
        val params = buildJsonObject {
            config.database?.takeIf { it.isNotBlank() }?.let { put("db", it) }
            put("login", login)
            put("password", password)
        }
        val payload = buildJsonObject {
            put("jsonrpc", "2.0")
            put("method", "call")
            put("params", params)
        }
        val request = Request.Builder()
            .url(url("/web/session/authenticate"))
            .post(payload.toString().toRequestBody(JSON_MEDIA))
            .build()
        val (code, body) = execute(request)
        if (code !in 200..299) throw failure(code, body)
        val root = runCatching { ApiJson.parseToJsonElement(body).jsonObject }.getOrNull()
            ?: throw ApiException(code, "Respons login tidak dapat dibaca")
        if (root["error"] != null) throw ApiException(401, "Nama pengguna atau kata sandi ditolak server")
        val uid = root["result"]?.jsonObject?.get("uid")?.jsonPrimitive?.contentOrNull
        if (uid == null || uid == "false" || uid == "null") {
            throw ApiException(401, "Nama pengguna atau kata sandi salah")
        }
    }

    suspend fun bootstrap(): IdentityDto {
        val (code, body) = execute(Request.Builder().url(url("/api/v1/me/bootstrap")).get().build())
        if (code !in 200..299) throw failure(code, body)
        return ApiJson.decodeFromString(IdentityDto.serializer(), body)
    }

    /** Mengembalikan JSON mentah (disimpan utuh) bersama hasil parse bagian yang dipakai. */
    suspend fun snapshot(): Pair<String, SnapshotDto> {
        val (code, body) = execute(Request.Builder().url(url("/api/v1/sync/snapshot")).get().build())
        if (code !in 200..299) throw failure(code, body)
        return body to ApiJson.decodeFromString(SnapshotDto.serializer(), body)
    }

    /** Mengirim envelope command apa adanya. UUID klien harus sama pada setiap retry. */
    suspend fun postCommand(payloadJson: String, csrfToken: String?): ReceiptDto {
        val builder = Request.Builder()
            .url(url("/api/v1/sync/commands"))
            .post(payloadJson.toRequestBody(JSON_MEDIA))
        if (csrfToken != null) builder.header("X-CSRF-Token", csrfToken)
        val (code, body) = execute(builder.build())
        if (code !in 200..299) throw failure(code, body)
        return ApiJson.decodeFromString(ReceiptDto.serializer(), body)
    }

    /**
     * Unggah bukti foto resmi (multipart). Token CSRF wajib; tanpa token sesi dianggap tidak valid.
     * Field `mode` tidak pernah dikirim oleh klien native.
     */
    suspend fun uploadEvidence(metadataJson: String, photo: File, csrfToken: String?): EvidenceReceiptDto {
        if (csrfToken == null) throw ApiException(401, "Sesi tidak memiliki token CSRF")
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("metadata", metadataJson)
            .addFormDataPart("photo", photo.name, photo.asRequestBody("image/jpeg".toMediaType()))
            .addFormDataPart("csrf_token", csrfToken)
            .build()
        val (code, text) = execute(Request.Builder().url(url("/api/v1/evidence")).post(body).build())
        if (code !in 200..299) throw failure(code, text)
        return ApiJson.decodeFromString(EvidenceReceiptDto.serializer(), text)
    }

    fun clearSession() {
        jar.clear()
        store.clearSession()
    }

    private companion object {
        val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()
    }
}
