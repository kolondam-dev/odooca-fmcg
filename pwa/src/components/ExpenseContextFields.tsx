import { useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
// References come from the assigned manifest when available. A blank manifest
// never invents a trip/DO; server validation remains authoritative.
export function ExpenseContextFields({
    deliveries,
    trip,
}: {
    deliveries: Snapshot["deliveries"];
    trip?: string;
}) {
    const [scope, setScope] = useState("trip");
    const [selected, setSelected] = useState(trip ?? deliveries[0]?.trip ?? "");
    const trips = [...new Set(deliveries.map((d) => d.trip))];
    const assigned = deliveries.filter((d) => d.trip === selected);
    return (
        <>
            <label>
                Lingkup biaya
                <select
                    name="scope"
                    value={scope}
                    onChange={(e) => setScope(e.currentTarget.value)}
                >
                    <option value="trip">Biaya perjalanan / trip</option>
                    <option value="delivery">Biaya per pengiriman / DO</option>
                </select>
            </label>
            <label>
                Referensi trip / perjalanan
                {trips.length ? (
                    <select
                        name="trip"
                        required
                        value={selected}
                        onChange={(e) => setSelected(e.currentTarget.value)}
                    >
                        {trips.map((t) => (
                            <option key={t} value={t}>
                                {t}
                            </option>
                        ))}
                    </select>
                ) : (
                    <input
                        name="trip"
                        required
                        maxLength={100}
                        value={selected}
                        onInput={(e) => setSelected(e.currentTarget.value)}
                    />
                )}
            </label>
            {scope === "delivery" && (
                <label>
                    Referensi DO (untuk biaya per pengiriman)
                    {deliveries.length ? (
                        <select name="delivery" required key={selected}>
                            <option value="">Pilih pengiriman</option>
                            {assigned.map((d) => (
                                <option key={d.id} value={d.id}>
                                    {d.id} · {d.outlet}
                                </option>
                            ))}
                        </select>
                    ) : (
                        <input name="delivery" required maxLength={100} />
                    )}
                </label>
            )}
        </>
    );
}
