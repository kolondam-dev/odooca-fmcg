plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

val baseUrl = (project.findProperty("odooca.baseUrl") as String?).orEmpty()
val uiFixture = project.findProperty("odooca.uiFixture") == "true"
val b09Resources = project.findProperty("odooca.b09Resources") as String?
val database = (project.findProperty("odooca.database") as String?).orEmpty()

android {
    namespace = "com.kolondam.odooca.field"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.kolondam.odooca.field"
        // minSdk = 24 adalah titik awal. Nilai final HARUS ditetapkan dari uji perangkat nyata
        // (Redmi 4X dan POCO M3) sesuai blueprint, bukan tebakan.
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "BASE_URL", "\"$baseUrl\"")
        buildConfigField("String", "DATABASE", "\"$database\"")
    }

    if (uiFixture) {
        sourceSets["debug"].res.srcDir("src/uiFixture/res")
    }

    if (b09Resources != null) {
        require(!uiFixture && baseUrl == "https://127.0.0.1:18443" && database.startsWith("fmcg_staging_"))
        sourceSets["debug"].res.srcDir(b09Resources)
    }

    buildTypes {
        debug {
            if (uiFixture) {
                buildConfigField("String", "BASE_URL", "\"http://127.0.0.1:18080\"")
                buildConfigField("String", "DATABASE", "\"ui-test\"")
            }
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(project(":core:domain"))
    implementation(project(":core:designsystem"))
    implementation(project(":core:data"))
    coreLibraryDesugaring(libs.android.desugar)

    val bom = platform(libs.androidx.compose.bom)
    implementation(bom)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.foundation)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.kotlinx.coroutines.android)
    debugImplementation(libs.androidx.compose.ui.tooling)
    androidTestImplementation(bom)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.uiautomator)
}
