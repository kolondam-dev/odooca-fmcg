package com.kolondam.odooca.field.domain.time

import com.kolondam.odooca.field.domain.json.JsonText
import com.kolondam.odooca.field.domain.json.jsonObject
import java.time.Instant
import java.util.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class IsoTest {
    @Test
    fun epochAndKnownInstants() {
        assertEquals("1970-01-01T00:00:00.000Z", Iso.formatUtc(0))
        assertEquals("2024-02-29T23:59:59.999Z", Iso.formatUtc(Instant.parse("2024-02-29T23:59:59.999Z").toEpochMilli()))
        assertEquals("1969-12-31T23:59:59.999Z", Iso.formatUtc(-1))
    }

    @Test
    fun formatMatchesJavaTimeAndRoundTripsForRandomValues() {
        val rnd = Random(42)
        repeat(5_000) {
            val ms = (rnd.nextLong() % 4_000_000_000_000L) // sekitar tahun 1843 sampai 2096
            val text = Iso.formatUtc(ms)
            assertEquals(ms, Instant.parse(text).toEpochMilli(), "format $ms -> $text")
            assertEquals(ms, Iso.parseUtc(text), "parse $text")
        }
    }

    @Test
    fun parseAcceptsOptionalFractionAndRejectsInvalid() {
        assertEquals(Instant.parse("2026-11-15T10:20:30Z").toEpochMilli(), Iso.parseUtc("2026-11-15T10:20:30Z"))
        assertEquals(Instant.parse("2026-11-15T10:20:30.5Z").toEpochMilli(), Iso.parseUtc("2026-11-15T10:20:30.5Z"))
        assertNull(Iso.parseUtc("2026-11-15T10:20:30+07:00"))
        assertNull(Iso.parseUtc("2023-02-29T00:00:00Z"))
        assertNull(Iso.parseUtc("2026-13-01T00:00:00Z"))
        assertNull(Iso.parseUtc("2026-11-15T24:00:00Z"))
        assertNull(Iso.parseUtc("kemarin"))
    }

    @Test
    fun dateValidationUsesRealCalendar() {
        assertTrue(Iso.isValidDate("2024-02-29"))
        assertFalse(Iso.isValidDate("2023-02-29"))
        assertFalse(Iso.isValidDate("1900-02-29"))
        assertTrue(Iso.isValidDate("2000-02-29"))
        assertFalse(Iso.isValidDate("2026-04-31"))
        assertFalse(Iso.isValidDate("2026-4-1"))
    }
}

class JsonTest {
    @Test
    fun quoteEscapesSpecials() {
        assertEquals("\"a\\\"b\\\\c\\n\\t\"", JsonText.quote("a\"b\\c\n\t"))
        assertEquals("\"\\u0001\"", JsonText.quote("\u0001"))
        assertEquals("\"Üñí 日本\"", JsonText.quote("Üñí 日本"))
    }

    @Test
    fun numbersAreNeverScientific() {
        assertEquals(0.00001, JsonText.number(1.0E-5).toDouble(), 0.0)
        assertTrue('E' !in JsonText.number(1.0E-5) && 'e' !in JsonText.number(1.0E-5))
        assertEquals("124.8428", JsonText.number(124.8428))
        assertEquals("1.0", JsonText.number(1.0))
        assertEquals("10000000000", JsonText.number(1.0E10))
    }

    @Test
    fun builderNestsInOrder() {
        val json = jsonObject {
            put("a", 1)
            put("b", "x")
            putObject("c") { put("d", true) }
            putStrings("e", listOf("p", "q"))
            put("f", 2.5)
        }
        assertEquals("{\"a\":1,\"b\":\"x\",\"c\":{\"d\":true},\"e\":[\"p\",\"q\"],\"f\":2.5}", json)
    }
}
