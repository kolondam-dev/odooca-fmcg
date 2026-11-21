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

val contractSamples = layout.buildDirectory.dir("contract-samples")

tasks.test {
    useJUnit()
    // Tes mengeluarkan contoh payload ke sini untuk divalidasi terhadap skema OpenAPI (tools/validate_contract.py).
    outputs.dir(contractSamples).withPropertyName("contractSamples")
    systemProperty("contract.out", contractSamples.get().asFile.absolutePath)
}
