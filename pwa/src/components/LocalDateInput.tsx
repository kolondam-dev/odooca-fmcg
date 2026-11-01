import { useState } from "preact/hooks";
export function LocalDateInput({
    name,
    label,
}: {
    name: string;
    label: string;
}) {
    const [value, setValue] = useState("");
    const parsed = /^\d{4}-\d{2}-\d{2}$/.test(value)
        ? new Date(`${value}T12:00:00Z`)
        : undefined;
    return (
        <label>
            {label}
            <input
                name={name}
                type="date"
                required
                lang="id"
                value={value}
                onInput={(e) => setValue(e.currentTarget.value)}
            />
            {parsed && !Number.isNaN(parsed.getTime()) && (
                <small>
                    {parsed.toLocaleDateString("id-ID", {
                        day: "numeric",
                        month: "long",
                        year: "numeric",
                        timeZone: "UTC",
                    })}
                </small>
            )}
        </label>
    );
}
