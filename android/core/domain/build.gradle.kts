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
    // Deklarasikan contoh kontrak sebagai output agar ikut dipulihkan dari build cache; tanpa ini tes yang
    // FROM-CACHE tidak menulis ulang contoh dan tools/validate_contract.py gagal (FileNotFoundError).
    outputs.dir(layout.buildDirectory.dir("contract-samples"))
}
