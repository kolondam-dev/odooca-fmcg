import { useState } from "preact/hooks";
import {
    Button,
    Checkbox,
    Chip,
    Field,
    IconButton,
    Progress,
    RadioRow,
    Segmented,
    Select,
    StatusDot,
    Stepper,
} from "./index";

/** Galeri atom untuk pengembangan. Dibuka dengan #ui; tidak ikut build produksi. */
export function Gallery() {
    const [method, setMethod] = useState<"tunai" | "giro" | "transfer">(
        "transfer",
    );
    const [qty, setQty] = useState(10);
    const [checked, setChecked] = useState(true);
    const [reason, setReason] = useState("uang");
    const [source, setSource] = useState("program");
    return (
        <main
            style={{
                maxWidth: "390px",
                margin: "0 auto",
                padding: "16px",
                display: "grid",
                gap: "16px",
            }}
        >
            <h1 style={{ font: "700 20px/28px var(--font)", margin: 0 }}>
                Galeri atom
            </h1>
            <Button icon="check">Simpan</Button>
            <Button variant="sec" size="md">
                Sekunder
            </Button>
            <Button variant="danger" size="sm">
                Tolak
            </Button>
            <Button disabled>Nonaktif</Button>
            <Button variant="sec" disabled size="md">
                Sekunder nonaktif
            </Button>
            <div style={{ display: "flex", gap: "8px" }}>
                <IconButton icon="sync" label="Sinkron" box />
                <IconButton icon="bell" label="Notifikasi" badge={3} />
                <IconButton icon="close" label="Tutup" disabled />
                <StatusDot online />
                <StatusDot online={false} />
            </div>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                <Chip tone="ok" icon="check">
                    Selesai
                </Chip>
                <Chip tone="warn">Menunggu</Chip>
                <Chip tone="bad">Gagal</Chip>
                <Chip tone="info">Info</Chip>
                <Chip>Netral</Chip>
            </div>
            <Field label="Nama pembayar" value="Ibu Sri Rejeki" />
            <Field
                label="Referensi transfer"
                error="Wajib diisi untuk transfer"
                value=""
            />
            <Field label="Alamat" value="Kantor MDU Manado" readOnly />
            <Select
                label="Sumber diskon"
                value={source}
                onChange={setSource}
                options={[
                    { value: "program", label: "Program" },
                    { value: "pengajuan", label: "Pengajuan" },
                ]}
            />
            <Segmented
                label="Metode bayar"
                value={method}
                onChange={setMethod}
                items={[
                    { value: "tunai", label: "Tunai" },
                    { value: "giro", label: "Giro" },
                    { value: "transfer", label: "Transfer" },
                ]}
            />
            <Checkbox checked={checked} onChange={setChecked}>
                INV-2026-03156
            </Checkbox>
            <div>
                <RadioRow
                    name="alasan"
                    value="uang"
                    label="Toko tidak punya uang"
                    selected={reason === "uang"}
                    onSelect={setReason}
                />
                <RadioRow
                    name="alasan"
                    value="tutup"
                    label="Toko tutup"
                    selected={reason === "tutup"}
                    onSelect={setReason}
                />
            </div>
            <Stepper value={qty} onChange={setQty} max={12} unit="karton" />
            <Progress value={60} label="Kunjungan" />
            <Progress value={100} tone="ok" label="Selesai" />
        </main>
    );
}
