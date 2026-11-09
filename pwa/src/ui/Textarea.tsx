import { cx } from "./cx";

export type TextareaProps = {
    label: string;
    value: string;
    onInput: (value: string) => void;
    hint?: string;
    rows?: number;
    required?: boolean;
    minLength?: number;
    maxLength?: number;
    disabled?: boolean;
    placeholder?: string;
    class?: string;
};

/** Isian beberapa baris; label di atas, teks 16 px. */
export function Textarea({
    label,
    value,
    onInput,
    hint,
    rows = 3,
    class: className,
    ...rest
}: TextareaProps) {
    return (
        <label class={cx("ui-field", className)}>
            <span class="ui-field__label">{label}</span>
            <textarea
                {...rest}
                class="ui-field__input ui-field__input--area"
                rows={rows}
                value={value}
                onInput={(event) =>
                    onInput((event.currentTarget as HTMLTextAreaElement).value)
                }
            />
            {hint ? <span class="ui-field__msg">{hint}</span> : null}
        </label>
    );
}
