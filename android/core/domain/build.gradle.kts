plugins {
    alias(libs.plugins.kotlin.jvm)
}

kotlin {
    jvmToolchain(17)
    compilerOptions { allWarningsAsErrors.set(true) }
}

dependencies {
    testImplementation(libs.kotlin.test)
    testImplementation(libs.kotlin.test.junit)
}

tasks.test {
    useJUnit()
    // Tes mengeluarkan contoh payload ke sini untuk divalidasi terhadap skema OpenAPI (tools/validate_contract.py).
    systemProperty("contract.out", layout.buildDirectory.dir("contract-samples").get().asFile.absolutePath)
}
