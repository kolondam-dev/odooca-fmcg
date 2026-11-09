/** Gabungkan nama kelas; nilai falsy dibuang. */
export function cx(...parts: Array<string | false | null | undefined>): string {
    return parts.filter(Boolean).join(" ");
}

/** Jepit angka ke rentang [min, max]. */
export function clamp(value: number, min: number, max: number): number {
    return Math.min(max, Math.max(min, value));
}

/** Nilai berikutnya untuk stepper, selalu dalam rentang. */
export function stepValue(
    value: number,
    delta: number,
    min: number,
    max: number,
): number {
    return clamp(value + delta, min, max);
}
