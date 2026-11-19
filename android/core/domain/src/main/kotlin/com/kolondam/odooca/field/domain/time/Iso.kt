package com.kolondam.odooca.field.domain.time

import java.util.Locale

/** Format dan parse waktu ISO-8601 UTC tanpa java.time, sehingga aman di Android lama tanpa desugaring. */
object Iso {
    private const val DAY_MS = 86_400_000L
    private val INSTANT = Regex("^(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2}):(\\d{2})(?:\\.(\\d{1,9}))?Z$")
    private val DATE = Regex("^(\\d{4})-(\\d{2})-(\\d{2})$")

    /** `yyyy-MM-ddTHH:mm:ss.SSSZ` dalam UTC. */
    fun formatUtc(epochMs: Long): String {
        val days = Math.floorDiv(epochMs, DAY_MS)
        val msOfDay = Math.floorMod(epochMs, DAY_MS)
        val (y, m, d) = civilFromDays(days)
        val h = msOfDay / 3_600_000
        val mi = (msOfDay / 60_000) % 60
        val s = (msOfDay / 1_000) % 60
        val ms = msOfDay % 1_000
        return String.format(Locale.ROOT, "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ", y, m, d, h, mi, s, ms)
    }

    /** Mengembalikan null bila format atau kalender tidak valid. */
    fun parseUtc(text: String): Long? {
        val m = INSTANT.matchEntire(text) ?: return null
        val g = m.groupValues
        val y = g[1].toInt(); val mo = g[2].toInt(); val d = g[3].toInt()
        val h = g[4].toInt(); val mi = g[5].toInt(); val s = g[6].toInt()
        if (!isValidCalendarDate(y, mo, d) || h > 23 || mi > 59 || s > 59) return null
        val ms = if (g[7].isEmpty()) 0 else (g[7] + "00").substring(0, 3).toInt()
        return daysFromCivil(y, mo, d) * DAY_MS + h * 3_600_000L + mi * 60_000L + s * 1_000L + ms
    }

    fun isValidDate(text: String): Boolean {
        val m = DATE.matchEntire(text) ?: return false
        return isValidCalendarDate(m.groupValues[1].toInt(), m.groupValues[2].toInt(), m.groupValues[3].toInt())
    }

    private fun isValidCalendarDate(y: Int, m: Int, d: Int): Boolean {
        if (m !in 1..12 || d < 1) return false
        val leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
        val days = when (m) {
            2 -> if (leap) 29 else 28
            4, 6, 9, 11 -> 30
            else -> 31
        }
        return d <= days
    }

    // Algoritma civil-from-days dan days-from-civil (Howard Hinnant).
    private fun civilFromDays(days: Long): Triple<Int, Int, Int> {
        val z = days + 719_468
        val era = Math.floorDiv(z, 146_097L)
        val doe = z - era * 146_097
        val yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365
        val y = yoe + era * 400
        val doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
        val mp = (5 * doy + 2) / 153
        val d = doy - (153 * mp + 2) / 5 + 1
        val m = if (mp < 10) mp + 3 else mp - 9
        return Triple((y + if (m <= 2) 1 else 0).toInt(), m.toInt(), d.toInt())
    }

    private fun daysFromCivil(y0: Int, m: Int, d: Int): Long {
        val y = (if (m <= 2) y0 - 1 else y0).toLong()
        val era = Math.floorDiv(y, 400L)
        val yoe = y - era * 400
        val mp = (if (m > 2) m - 3 else m + 9).toLong()
        val doy = (153 * mp + 2) / 5 + d - 1
        val doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
        return era * 146_097 + doe - 719_468
    }
}
