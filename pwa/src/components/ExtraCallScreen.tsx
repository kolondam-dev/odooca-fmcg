import { useMemo, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import {
    Button,
    Callout,
    Card,
    Field,
    ListRow,
    Screen,
    ScreenHeader,
    Select,
    Textarea,
} from "../ui";
import { useBackLayer } from "../ui/navigation";

export const EXTRA_REASONS = [
    { value: "store_request", label: "Permintaan toko" },
    { value: "stock_follow_up", label: "Tindak lanjut stok" },
    { value: "collection", label: "Penagihan" },
    { value: "promo", label: "Promo / pengenalan produk" },
    { value: "other", label: "Lainnya" },
];

/** Layar penuh Extra call (DS: Extra_call). Kunjungan di luar PJP, butuh approval supervisor. */
export function ExtraCallScreen({
    snapshot,
    submit,
    close,
}: {
    snapshot: Snapshot;
    submit: (
        type: "sales.extra_call.request",
        payload: Record<string, unknown>,
        label: string,
    ) => Promise<unknown>;
    close: () => void;
}) {
    useBackLayer(true, close);
    const directory = snapshot.extra_call_outlets;
    const [query, setQuery] = useState("");
    const [picked, setPicked] = useState<string>();
    const [freeName, setFreeName] = useState("");
    const [reason, setReason] = useState(EXTRA_REASONS[0]!.value);
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const matches = useMemo(() => {
        const q = query.trim().toLocaleLowerCase("id");
        return (directory ?? [])
            .filter((o) =>
                `${o.name} ${o.address}`.toLocaleLowerCase("id").includes(q),
            )
            .slice(0, 20);
    }, [directory, query]);
    const outlet = directory?.find((o) => o.id === picked);
    const name = directory ? (outlet?.name ?? "") : freeName.trim();
    async function send() {
        if (busy) return;
        setError("");
        if (!name) {
            setError("Pilih outlet untuk extra call.");
            return;
        }
        const label = EXTRA_REASONS.find((r) => r.value === reason)!.label;
        setBusy(true);
        try {
            await submit(
                "sales.extra_call.request",
                {
                    ...(outlet ? { outlet_id: outlet.id } : {}),
                    outlet_name: name,
                    reason_code: reason,
                    reason: note.trim() ? `${label}: ${note.trim()}` : label,
                    ...(note.trim() ? { note: note.trim() } : {}),
                },
                `Extra call • ${name}`,
            );
            close();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Gagal menyimpan.");
        } finally {
            setBusy(false);
        }
    }
    return (
        <Screen
            label="Extra call"
            class="ui-screen--over"
            header={<ScreenHeader title="Extra call" onBack={close} />}
            footer={
                <Button icon="plus" disabled={busy} onClick={() => void send()}>
                    {busy ? "Menyimpan…" : "Tambahkan ke daftar hari ini"}
                </Button>
            }
        >
            <Callout tone="info">
                Extra call adalah kunjungan di luar PJP. Tercatat terpisah di
                laporan harian.
            </Callout>
            {directory ? (
                <>
                    <Field
                        label="Cari outlet"
                        value={query}
                        onInput={setQuery}
                        placeholder="Nama atau alamat outlet"
                    />
                    <Card>
                        {matches.length ? (
                            matches.map((o, i) => (
                                <ListRow
                                    key={o.id}
                                    icon="store"
                                    title={o.name}
                                    sub={o.address}
                                    divider={i > 0}
                                    status={
                                        o.id === picked
                                            ? { tone: "ok", label: "Dipilih" }
                                            : undefined
                                    }
                                    onClick={() => setPicked(o.id)}
                                />
                            ))
                        ) : (
                            <p class="ui-field__hint">
                                Outlet tidak ditemukan.
                            </p>
                        )}
                    </Card>
                </>
            ) : (
                <Field
                    label="Nama outlet"
                    value={freeName}
                    onInput={setFreeName}
                    maxLength={100}
                    hint="Daftar outlet belum tersedia dari server; isi nama outlet."
                />
            )}
            <Select
                label="Alasan"
                options={EXTRA_REASONS}
                value={reason}
                onChange={setReason}
            />
            <Textarea
                label="Catatan (opsional)"
                value={note}
                onInput={setNote}
                maxLength={400}
                placeholder="Contoh: toko minta kirim stok tambahan"
            />
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
        </Screen>
    );
}
