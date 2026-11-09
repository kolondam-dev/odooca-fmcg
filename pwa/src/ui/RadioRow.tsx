import { cx } from "./cx";

/** Satu pilihan dalam grup radio; satu baris penuh dapat disentuh. */
export function RadioRow({
    name,
    value,
    selected,
    onSelect,
    label,
}: {
    name: string;
    value: string;
    selected: boolean;
    onSelect: (value: string) => void;
    label: string;
}) {
    return (
        <label class={cx("ui-radio", selected && "is-on")}>
            <input
                type="radio"
                name={name}
                value={value}
                checked={selected}
                onChange={() => onSelect(value)}
            />
            {label}
        </label>
    );
}
