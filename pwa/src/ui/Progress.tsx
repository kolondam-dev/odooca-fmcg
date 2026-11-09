import { clamp } from "./cx";

export type ProgressTone = "pri" | "ok" | "warn" | "bad";

/** Bilah kemajuan 0–100 dengan role=progressbar. */
export function Progress({
    value,
    tone = "pri",
    label,
}: {
    value: number;
    tone?: ProgressTone;
    label: string;
}) {
    const pct = Math.round(clamp(value, 0, 100));
    return (
        <div
            class="ui-progress"
            role="progressbar"
            aria-label={label}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
        >
            <i
                class={`ui-progress__bar ui-progress__bar--${tone}`}
                style={{ width: `${pct}%` }}
            />
        </div>
    );
}
