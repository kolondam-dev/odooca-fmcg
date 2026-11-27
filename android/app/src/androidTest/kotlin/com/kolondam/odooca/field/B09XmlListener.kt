package com.kolondam.odooca.field

import android.util.Xml
import androidx.test.platform.app.InstrumentationRegistry
import java.util.UUID
import org.junit.runner.Description
import org.junit.runner.Result
import org.junit.runner.notification.Failure
import org.junit.runner.notification.RunListener

/** Writes only the actual test IDs and outcomes, without runner arguments or exception details. */
class B09XmlListener : RunListener() {
    private val started = mutableListOf<Description>()
    private val failed = mutableSetOf<Description>()
    private val skipped = mutableListOf<Description>()

    override fun testStarted(description: Description) {
        started += description
    }

    override fun testFailure(failure: Failure) {
        failed += failure.description
    }

    override fun testAssumptionFailure(failure: Failure) {
        skipped += failure.description
    }

    override fun testIgnored(description: Description) {
        skipped += description
    }

    override fun testRunFinished(result: Result) {
        val args = InstrumentationRegistry.getArguments()
        val uuid = requireNotNull(args.getString("uuid"))
        require(UUID.fromString(uuid).let { it.version() == 4 && it.toString() == uuid })
        val phase = args.getString("phase")
        require(phase == "first" || phase == "replay")
        val file = InstrumentationRegistry.getInstrumentation().targetContext.filesDir
            .resolve("b09-$uuid-$phase.xml")
        file.outputStream().use { stream ->
            val xml = Xml.newSerializer()
            xml.setOutput(stream, "UTF-8")
            xml.startDocument("UTF-8", null)
            xml.startTag(null, "testsuite")
            xml.attribute(null, "uuid", uuid)
            xml.attribute(null, "phase", phase)
            xml.attribute(null, "tests", result.runCount.toString())
            xml.attribute(null, "failures", result.failureCount.toString())
            xml.attribute(null, "skipped", skipped.size.toString())
            for (test in started + skipped.filterNot(started::contains)) {
                xml.startTag(null, "testcase")
                xml.attribute(null, "classname", test.className.orEmpty())
                xml.attribute(null, "name", test.methodName.orEmpty())
                val outcome = when (test) {
                    in failed -> "failure"
                    in skipped -> "skipped"
                    else -> null
                }
                if (outcome != null) {
                    xml.startTag(null, outcome)
                    xml.endTag(null, outcome)
                }
                xml.endTag(null, "testcase")
            }
            xml.endTag(null, "testsuite")
            xml.endDocument()
        }
    }
}
