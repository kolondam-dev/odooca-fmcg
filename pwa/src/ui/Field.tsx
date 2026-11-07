import type { InputHTMLAttributes, LooseInputHTMLAttributes } from "preact";
import { cx } from "./cx";

export type FieldProps = {
    label: string;
    value?: string | number;
    onInput?: (value: string) => void;
    hint?: string;
    /** Pesan galat; menandai input tidak valid. */
    error?: string;
    type?: "text" | "email" | "password" | "tel" | "search" | "url" | "date";
    inputMode?: "text" | "numeric" | "decimal" | "tel" | "email" | "search";
    name?: string;
    placeholder?: string;
    autoComplete?: string;
    autoCapitalize?: "none" | "sentences" | "words" | "characters";
    spellcheck?: boolean;
    maxLength?: number;
    readOnly?: boolean;
    disabled?: boolean;
    required?: boolean;
    class?: string;
};

/** Isian satu baris: label di atas, tinggi 48 px, teks 16 px (mencegah zoom iOS). */
export function Field({
    label,
    value,
    onInput,
    hint,
    error,
    class: className,
    ...rest
}: FieldProps) {
    const inputProps: LooseInputHTMLAttributes<HTMLInputElement> = {
        ...rest,
        class: "ui-field__input",
        value,
        "aria-invalid": error ? "true" : undefined,
        onInput: onInput
            ? (event) =>
                  onInput((event.currentTarget as HTMLInputElement).value)
            : undefined,
    };
    return (
        <label class={cx("ui-field", className)}>
            <span class="ui-field__label">{label}</span>
            {/* Preact 11 mengetik input sebagai gabungan per type; props di atas sudah dibatasi FieldProps. */}
            <input
                {...(inputProps as unknown as InputHTMLAttributes<HTMLInputElement>)}
            />
            {error ? (
                <span class="ui-field__msg ui-field__msg--bad" role="alert">
                    {error}
                </span>
            ) : hint ? (
                <span class="ui-field__msg">{hint}</span>
            ) : null}
        </label>
    );
}
