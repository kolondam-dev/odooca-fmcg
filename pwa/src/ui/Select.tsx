import { cx } from "./cx";

export type SelectOption = { value: string; label: string };

export type SelectProps = {
    label: string;
    options: SelectOption[];
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    name?: string;
    disabled?: boolean;
    class?: string;
};

/** Pilihan tunggal memakai select asli agar papan pilih ponsel dan pembaca layar bekerja. */
export function Select({
    label,
    options,
    value,
    onChange,
    placeholder,
    name,
    disabled,
    class: className,
}: SelectProps) {
    return (
        <label class={cx("ui-field", className)}>
            <span class="ui-field__label">{label}</span>
            <select
                class="ui-select"
                name={name}
                disabled={disabled}
                value={value}
                onChange={(event) =>
                    onChange((event.currentTarget as HTMLSelectElement).value)
                }
            >
                {placeholder ? (
                    <option value="" disabled>
                        {placeholder}
                    </option>
                ) : null}
                {options.map((option) => (
                    <option key={option.value} value={option.value}>
                        {option.label}
                    </option>
                ))}
            </select>
        </label>
    );
}
