# kotlinx.serialization: pertahankan serializer yang dihasilkan plugin.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class com.kolondam.odooca.field.** { kotlinx.serialization.KSerializer serializer(...); }
-keep,includedescriptorclasses class com.kolondam.odooca.field.**$$serializer { *; }
