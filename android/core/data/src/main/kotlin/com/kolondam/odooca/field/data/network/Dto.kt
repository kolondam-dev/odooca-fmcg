package com.kolondam.odooca.field.data.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

val ApiJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    encodeDefaults = true
}

/** `GET /api/v1/me/bootstrap` */
@Serializable
data class IdentityDto(
    val id: String,
    val companyId: String,
    val companyName: String? = null,
    val name: String,
    val title: String = "",
    val roles: List<String> = emptyList(),
    val capabilities: List<String> = emptyList(),
    val businessDate: String,
    val csrfToken: String? = null,
)

@Serializable
data class ScopeDto(
    @SerialName("company_id") val companyId: String,
    @SerialName("user_id") val userId: String,
    @SerialName("warehouse_id") val warehouseId: String,
    @SerialName("business_date") val businessDate: String,
)

@Serializable
data class OutletDto(
    val id: String,
    val name: String,
    val channel: String = "",
    val address: String = "",
    val distance: String = "",
    val time: String = "",
    val latitude: Double,
    val longitude: Double,
    val radius: Double,
    @SerialName("image_url") val imageUrl: String? = null,
)

@Serializable
data class ProductDto(
    val id: String,
    val name: String,
    val brand: String = "",
    val principal: String = "",
    val unit: String = "",
    val price: Double = 0.0,
    val stock: Double = 0.0,
)

/** `GET /api/v1/sync/snapshot` (bagian yang dipakai fondasi; field lain diabaikan dulu). */
@Serializable
data class SnapshotDto(
    val version: String,
    val updatedAt: String,
    val warehouseName: String? = null,
    val scope: ScopeDto? = null,
    val outlets: List<OutletDto> = emptyList(),
    val products: List<ProductDto> = emptyList(),
)

/** Respons `POST /api/v1/evidence` (bagian yang dipakai klien). */
@Serializable
data class EvidenceReceiptDto(
    @SerialName("client_uuid") val clientUuid: String,
    @SerialName("binding_sha256") val bindingSha256: String,
    @SerialName("original_sha256") val originalSha256: String,
    @SerialName("watermarked_sha256") val watermarkedSha256: String,
    val latitude: Double,
    val longitude: Double,
    val accuracy: Double,
    @SerialName("photo_selected_at") val photoSelectedAt: String,
)

/** Respons `POST /api/v1/sync/commands`. */
@Serializable
data class ReceiptDto(
    @SerialName("client_uuid") val clientUuid: String,
    val status: String,
    val message: String = "",
    val reference: String = "",
)
