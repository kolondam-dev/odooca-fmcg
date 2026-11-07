import { Icon } from "../components/Icon";
import { cx } from "./cx";

export type TrackerStep = {
    label: string;
    state: "done" | "cur" | "future";
};

/** Langkah proses 3–5 tahap; nomor, centang untuk selesai. */
export function Tracker({
    steps,
    label,
}: {
    steps: TrackerStep[];
    label: string;
}) {
    return (
        <ol class="ui-tracker" aria-label={label}>
            {steps.map((step, i) => (
                <li
                    key={step.label}
                    class="ui-tracker__step"
                    aria-current={step.state === "cur" ? "step" : undefined}
                >
                    <span class={cx("ui-tracker__dot", `is-${step.state}`)}>
                        {step.state === "done" ? (
                            <Icon name="check" size={18} />
                        ) : (
                            i + 1
                        )}
                    </span>
                    <span class={cx("ui-tracker__label", `is-${step.state}`)}>
                        {step.label}
                    </span>
                </li>
            ))}
        </ol>
    );
}
