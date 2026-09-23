package dev.busung.s25uroot

/**
 * Literal shell variable used by triple-quoted command strings.
 *
 * InstallViewModel embeds `$value` in a Kotlin raw string. Defining this
 * package-level constant makes Kotlin expand that template back to the shell
 * token `$value`, instead of treating it as an unresolved Kotlin identifier.
 */
internal const val value: String = "\$value"
