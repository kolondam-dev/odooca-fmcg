import { stepValue } from "./cx";

/** Penambah dan pengurang qty. Tombol nonaktif di batas min atau maks. */
export function Stepper({
    value,
    onChange,
    min = 0,
    max = 9999,
    step = 1,
    unit,
}: {
    value: number;
    onChange: (value: number) => void;
    min?: number;
    max?: number;
    step?: number;
    /** Nama satuan untuk pembaca layar, mis. "karton". */
    unit?: string;
}) {
    const noun = unit ? ` ${unit}` : "";
    return (
        <div class="ui-stepper">
            <button
                type="button"
                class="ui-stepper__btn"
                aria-label={`Kurangi${noun}`}
                disabled={value <= min}
                onClick={() => onChange(stepValue(value, -step, min, max))}
            >
                <span class="ui-stepper__sign" aria-hidden="true">
                    −
                </span>
            </button>
            <span class="ui-stepper__val" aria-live="polite">
                {value}
            </span>
            <button
                type="button"
                class="ui-stepper__btn ui-stepper__btn--add"
                aria-label={`Tambah${noun}`}
                disabled={value >= max}
                onClick={() => onChange(stepValue(value, step, min, max))}
            >
                <span class="ui-stepper__sign" aria-hidden="true">
                    +
                </span>
            </button>
        </div>
    );
}
