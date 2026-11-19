package com.kolondam.odooca.field.data.network

/** Alamat backend Odoo. Tidak ada nilai bawaan: harus dikonfigurasi per lingkungan. */
data class ApiConfig(val baseUrl: String, val database: String?) {
    init {
        require(baseUrl.isBlank() || !baseUrl.endsWith("/")) { "baseUrl tidak boleh berakhir dengan garis miring" }
    }

    val isConfigured: Boolean get() = baseUrl.isNotBlank()
}
