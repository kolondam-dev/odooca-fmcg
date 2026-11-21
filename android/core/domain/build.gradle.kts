import org.gradle.process.CommandLineArgumentProvider

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

abstract class ContractSamplesArguments : CommandLineArgumentProvider {
    @get:OutputDirectory
    abstract val directory: DirectoryProperty

    override fun asArguments(): Iterable<String> =
        listOf("-Dcontract.out=${directory.get().asFile.absolutePath}")
}

tasks.test {
    useJUnit()
    // Cache the payloads alongside the test results without putting the checkout path in the cache key.
    jvmArgumentProviders.add(objects.newInstance<ContractSamplesArguments>().apply {
        directory.set(layout.buildDirectory.dir("contract-samples"))
    })
}
