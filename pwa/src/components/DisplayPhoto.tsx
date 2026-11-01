import { useContext } from "preact/hooks";
import { EvidenceIdentityContext } from "../ui/evidenceIdentity";
import { useEffect, useRef, useState } from "preact/hooks";
import type { FieldStore } from "../storage/store";
import type { EvidenceRef } from "./Evidence";
import { CameraViewfinder, type CameraCaptureResult } from "./CameraViewfinder";
import {
    compressEvidence,
    renderEvidencePackage,
} from "../domain/evidence-render";
import { Icon } from "./Icon";

/**
 * Local-only proof photo for an order signature (store display / shelf).
 * The order wire contract has no evidence field, so the packaged photo stays in
 * IndexedDB and is referenced by the order draft instead.
 */
export function DisplayPhoto({
    store,
    owner,
    outletName,
    coordinates,
    value,
    onChange,
    required = true,
}: {
    store: FieldStore;
    owner: string;
    outletName: string;
    coordinates?: { latitude: number; longitude: number };
    value?: EvidenceRef;
    onChange: (ref?: EvidenceRef) => void;
    required?: boolean;
}) {
    const identity = useContext(EvidenceIdentityContext);
    const [open, setOpen] = useState(false);
    const [preview, setPreview] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const generation = useRef(0);
    const fileInput = useRef<HTMLInputElement>(null);
    useEffect(
        () => () => {
            generation.current++;
        },
        [],
    );
    useEffect(() => {
        if (!value) {
            setPreview("");
            return;
        }
        let active = true;
        let url = "";
        void store
            .listEvidence(owner)
            .then((rows) => {
                const row = rows.find(
                    (e) =>
                        e.owner === owner &&
                        e.key === `${owner}:${value.id}` &&
                        e.capturedAt === value.capturedAt,
                );
                if (!active || !row) return;
                url = URL.createObjectURL(row.blob);
                setPreview(url);
            })
            .catch(() => {
                if (active) setError("Foto lokal tidak dapat dibuka.");
            });
        return () => {
            active = false;
            if (url) URL.revokeObjectURL(url);
        };
    }, [value, owner, store]);
    async function save(
        blob: Blob,
        fix: { latitude: number; longitude: number; accuracy: number },
        shotAt: string,
    ) {
        const ticket = ++generation.current;
        setOpen(false);
        setBusy(true);
        setError("");
        try {
            const capturedAt = new Date().toISOString();
            const next = {
                id: crypto.randomUUID(),
                latitude: fix.latitude,
                longitude: fix.longitude,
                accuracy: fix.accuracy,
                capturedAt,
            };
            const packaged = await renderEvidencePackage(
                blob,
                owner,
                next,
                shotAt,
                shotAt,
                __DEMO__,
                identity
                    ? { ...identity, address: `Tujuan: ${outletName}` }
                    : undefined,
            );
            if (generation.current !== ticket) return;
            await store.saveEvidence(packaged);
            if (generation.current !== ticket) return;
            onChange({ ...next, packageHash: packaged.visual!.bindingSha256 });
        } catch (e) {
            if (generation.current === ticket) {
                setError(
                    e instanceof Error ? e.message : "Foto gagal disimpan.",
                );
                onChange(undefined);
            }
        } finally {
            if (generation.current === ticket) setBusy(false);
        }
    }
    function fromCamera(result: CameraCaptureResult) {
        void save(
            result.blob,
            {
                latitude: result.latitude,
                longitude: result.longitude,
                accuracy: result.accuracy,
            },
            new Date(result.timestamp).toISOString(),
        );
    }
    async function fromFile(file?: File) {
        if (!file) return;
        if (!coordinates) {
            setError("Titik outlet tidak tersedia untuk foto display.");
            return;
        }
        setBusy(true);
        try {
            const blob = await compressEvidence(file);
            await save(
                blob,
                { ...coordinates, accuracy: 10 },
                new Date().toISOString(),
            );
        } catch (e) {
            setBusy(false);
            setError(e instanceof Error ? e.message : "Foto tidak valid.");
        }
    }
    return (
        <div class="display-photo">
            <div class="display-photo-head">
                <div>
                    <strong>Foto display{required ? "" : " (opsional)"}</strong>
                    <small>Rak/display outlet saat order ditandatangani.</small>
                </div>
                {value && (
                    <span class="pill green">
                        <Icon name="check" size={14} /> Tersimpan
                    </span>
                )}
            </div>
            {preview && (
                <img
                    class="photo-preview"
                    src={preview}
                    alt="Foto display outlet"
                />
            )}
            <div class="display-photo-actions">
                <button
                    type="button"
                    class="secondary"
                    disabled={busy}
                    onClick={() => setOpen(true)}
                >
                    <Icon name="camera" size={18} />
                    {value ? "Ambil ulang" : "Ambil foto"}
                </button>
                <button
                    type="button"
                    class="text-button"
                    disabled={busy}
                    onClick={() => fileInput.current?.click()}
                >
                    Unggah foto
                </button>
                <input
                    ref={fileInput}
                    aria-label="Foto display outlet"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    capture="environment"
                    style={{ display: "none" }}
                    onChange={(e) => void fromFile(e.currentTarget.files?.[0])}
                />
            </div>
            {busy && <p class="muted">Menyimpan foto di perangkat…</p>}
            {error && (
                <p role="alert" class="form-error">
                    {error}
                </p>
            )}
            {open && (
                <CameraViewfinder
                    title="Foto Display Outlet"
                    outletName={outletName}
                    salespersonName={identity?.employee}
                    rawCapture
                    defaultCoordinates={coordinates}
                    onCapture={fromCamera}
                    onClose={() => setOpen(false)}
                />
            )}
        </div>
    );
}
