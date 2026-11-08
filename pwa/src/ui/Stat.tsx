import type { ComponentChildren } from "preact";
import { Icon } from "../components/Icon";
import { cx } from "./cx";

/** Deretan angka ringkas (DS: stats). */
export function Stats({
    items,
}: {
    items: { value: ComponentChildren; label: string }[];
}) {
    return (
        <div class="ui-stats">
            {items.map((item) => (
                <div class="ui-stat" key={item.label}>
                    <span class="ui-stat__v">{item.value}</span>
                    <span class="ui-stat__l">{item.label}</span>
                </div>
            ))}
        </div>
    );
}

export type DayStepState = "done" | "active" | "lock";

/** Langkah hari kerja: selesai (centang), aktif (nomor), terkunci. */
export function DayStep({
    state,
    n,
    title,
    sub,
    right,
}: {
    state: DayStepState;
    n: number;
    title: string;
    sub?: string;
    right?: ComponentChildren;
}) {
    return (
        <div class="ui-dstep">
            <span class={cx("ui-dstep__dot", `is-${state}`)}>
                {state === "done" ? (
                    <Icon name="check" size={18} />
                ) : state === "lock" ? (
                    <Icon name="lock" size={16} />
                ) : (
                    n
                )}
            </span>
            <span class="ui-dstep__body">
                <span class="ui-dstep__title">{title}</span>
                {sub ? <span class="ui-dstep__sub">{sub}</span> : null}
            </span>
            {right}
        </div>
    );
}
