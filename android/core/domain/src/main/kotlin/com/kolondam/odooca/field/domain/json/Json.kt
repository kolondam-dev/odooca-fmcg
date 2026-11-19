package com.kolondam.odooca.field.domain.json

import java.math.BigDecimal
import java.util.Locale

/** Penulis JSON minimal tanpa dependensi, agar payload command bisa dibangun dan diuji di Kotlin murni. */
object JsonText {
    fun quote(s: String): String {
        val sb = StringBuilder(s.length + 2).append('"')
        for (c in s) {
            when {
                c == '"' -> sb.append("\\\"")
                c == '\\' -> sb.append("\\\\")
                c == '\n' -> sb.append("\\n")
                c == '\r' -> sb.append("\\r")
                c == '\t' -> sb.append("\\t")
                c == '\b' -> sb.append("\\b")
                c == '\u000C' -> sb.append("\\f")
                c < ' ' -> sb.append(String.format(Locale.ROOT, "\\u%04x", c.code))
                else -> sb.append(c)
            }
        }
        return sb.append('"').toString()
    }

    fun number(d: Double): String {
        require(d.isFinite()) { "Angka JSON harus terhingga" }
        return BigDecimal.valueOf(d).toPlainString()
    }
}

class JsonObjectBuilder {
    private val parts = ArrayList<String>()

    fun put(key: String, value: String) { parts += JsonText.quote(key) + ":" + JsonText.quote(value) }
    fun put(key: String, value: Double) { parts += JsonText.quote(key) + ":" + JsonText.number(value) }
    fun put(key: String, value: Int) { parts += JsonText.quote(key) + ":" + value }
    fun put(key: String, value: Boolean) { parts += JsonText.quote(key) + ":" + value }
    fun putObject(key: String, block: JsonObjectBuilder.() -> Unit) {
        parts += JsonText.quote(key) + ":" + jsonObject(block)
    }
    fun putStrings(key: String, values: List<String>) {
        parts += JsonText.quote(key) + ":[" + values.joinToString(",") { JsonText.quote(it) } + "]"
    }

    fun build(): String = "{" + parts.joinToString(",") + "}"
}

fun jsonObject(block: JsonObjectBuilder.() -> Unit): String = JsonObjectBuilder().apply(block).build()
