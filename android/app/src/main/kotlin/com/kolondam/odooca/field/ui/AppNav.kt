package com.kolondam.odooca.field.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.kolondam.odooca.field.AppContainer
import com.kolondam.odooca.field.ui.attendance.AttendanceApprovalScreen
import com.kolondam.odooca.field.ui.calibration.CalibrationScreen
import com.kolondam.odooca.field.ui.home.HomeScreen
import com.kolondam.odooca.field.ui.login.LoginScreen

private object Routes {
    const val LOGIN = "login"
    const val HOME = "home"
    const val ATTENDANCE_APPROVAL = "attendance_approval"
    const val CALIBRATION = "calibration"
}

@Composable
fun AppNav(container: AppContainer) {
    val nav = rememberNavController()
    val identity by container.session.identity.collectAsStateWithLifecycle()
    val start = if (identity != null) Routes.HOME else Routes.LOGIN

    // Sesi berakhir atau logout: kembali ke login dan kosongkan tumpukan layar.
    LaunchedEffect(identity == null) {
        if (identity == null && nav.currentDestination?.route != Routes.LOGIN) {
            nav.navigate(Routes.LOGIN) { popUpTo(0) }
        }
    }

    NavHost(navController = nav, startDestination = start) {
        composable(Routes.LOGIN) {
            LoginScreen(container) {
                nav.navigate(Routes.HOME) { popUpTo(Routes.LOGIN) { inclusive = true } }
            }
        }
        composable(Routes.HOME) {
            val current = identity ?: return@composable
            if ("attendance.approval_only" in current.capabilities) {
                val scope = rememberCoroutineScope()
                AttendanceApprovalScreen(container, current.id, { scope.launch { container.session.logout() } }, "Keluar")
            } else {
                HomeScreen(container, onOpenCalibration = { nav.navigate(Routes.CALIBRATION) },
                    onOpenApproval = { nav.navigate(Routes.ATTENDANCE_APPROVAL) })
            }
        }
        composable(Routes.ATTENDANCE_APPROVAL) {
            val current = identity ?: return@composable
            AttendanceApprovalScreen(container, current.id, { nav.popBackStack() }, "Kembali")
        }
        composable(Routes.CALIBRATION) {
            CalibrationScreen(onBack = { nav.popBackStack() })
        }
    }
}
