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
    // Deklarasikan contoh kontrak sebagai output agar ikut dipulihkan dari build cache; tanpa ini tes yang
    // FROM-CACHE tidak menulis ulang contoh dan tools/validate_contract.py gagal (FileNotFoundError).
    // Declare the directory as a task output so Gradle's build cache restores it
    // when :core:domain:test is FROM-CACHE in CI.
    val contractSamples = layout.buildDirectory.dir("contract-samples")
    systemProperty("contract.out", contractSamples.get().asFile.absolutePath)
    outputs.dir(contractSamples)
}
