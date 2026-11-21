package com.kolondam.odooca.field

import android.Manifest
import android.content.pm.PackageManager
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class InitialFlowTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun loginValidationResumeNavigationAndLocationDenial() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val device = UiDevice.getInstance(instrumentation)
        val scenario = compose.activityRule.scenario
        val login = compose.onNodeWithTag("login_user").assert(hasText("Pengguna"))
        val password = compose.onNodeWithTag("login_password").assert(hasText("Kata sandi"))
        val submit = compose.onNodeWithTag("login_submit").assert(hasText("Masuk"))

        compose.onNodeWithText("Masuk dengan akun Odoo Anda").assertIsDisplayed()
        submit.assertIsNotEnabled()
        scenario.moveToState(Lifecycle.State.CREATED)
        scenario.moveToState(Lifecycle.State.RESUMED)
        scenario.recreate()
        submit.assertIsNotEnabled()

        login.performTextInput("ui-test")
        password.performTextInput("wrong-value")
        dismissKeyboard(device)
        submit.assertIsEnabled().performClick()
        waitForText("Nama pengguna atau kata sandi salah")
        compose.onNodeWithText("Nama pengguna atau kata sandi salah").assertIsDisplayed()

        password.performTextClearance()
        password.performTextInput("ui-test-pass")
        dismissKeyboard(device)
        submit.assertIsEnabled().performClick()
        waitForText("Data 2026-11-19 • versi ui-test")
        compose.onNodeWithText("Belum ada outlet pada penugasan hari ini.").assertIsDisplayed()
        compose.onNodeWithText("Kalibrasi GPS perangkat").performClick()
        compose.onNodeWithText("Diam di area terbuka selama pengukuran").assertIsDisplayed()

        val context = instrumentation.targetContext
        assertEquals(
            PackageManager.PERMISSION_DENIED,
            context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION),
        )
        compose.onNodeWithText("Mulai pengukuran").performClick()
        val deny = device.wait(
            Until.findObject(By.res(Pattern.compile(".+:id/permission_deny_button"))),
            10_000,
        )
        assertNotNull("Dialog izin lokasi harus muncul", deny)
        requireNotNull(deny).click()
        waitForText("Catatan: PERMISSION_DENIED", substring = true)
        assertEquals(
            PackageManager.PERMISSION_DENIED,
            context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION),
        )
        compose.onNodeWithText("Kembali").performClick()
        compose.onNodeWithText("Kalibrasi GPS perangkat").assertIsDisplayed()
        compose.onNodeWithText("Keluar").performClick()
        waitForText("Masuk dengan akun Odoo Anda")
        compose.onNodeWithText("Masuk").assertIsNotEnabled()
    }

    private fun dismissKeyboard(device: UiDevice) {
        val activity = compose.activity
        val visible = compose.runOnIdle {
            ViewCompat.getRootWindowInsets(activity.window.decorView)
                ?.isVisible(WindowInsetsCompat.Type.ime()) == true
        }
        if (visible) device.pressBack()
    }

    private fun waitForText(text: String, substring: Boolean = false) {
        compose.waitUntil(15_000) {
            compose.onAllNodes(hasText(text, substring = substring)).fetchSemanticsNodes().isNotEmpty()
        }
    }
}
