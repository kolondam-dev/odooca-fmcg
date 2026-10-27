import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { z } from "zod";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";
import { assertLocalEvidence } from "../domain/evidence-package";
import {
    VisitEvidenceSchema,
    type VisitEvidence,
} from "../domain/visit-contracts";
import type { FieldStore } from "../storage/store";
const Slot = z
    .object({
        owner: z.string(),
        sessionId: z.string().uuid(),
        outletId: z.string(),
        phase: z.enum(["check_in", "check_out"]),
        visitId: z.string().uuid().nullable(),
        ref: VisitEvidenceSchema.nullable(),
    })
    .strict();
export function VisitPhotoField({
    store,
    owner,
    sessionId,
    outletId,
    phase,
    visitId,
    ready,
    disabled = false,
}: {
    store: FieldStore;
    owner: string;
    sessionId: string;
    outletId: string;
    phase: "check_in" | "check_out";
    visitId?: string;
    ready: (ref?: VisitEvidence) => void;
    disabled?: boolean;
}) {
    const key = `visit-photo-v1:${JSON.stringify([sessionId, outletId, phase, visitId ?? null])}`;
    const binding = {
        owner,
        sessionId,
        outletId,
        phase,
        visitId: visitId ?? null,
    };
    const [ref, setRef] = useState<VisitEvidence>();
    const [durable, setDurable] = useState(false);
    const [loading, setLoading] = useState(true),
        [error, setError] = useState("");
    const generation = useRef(0);
    useLayoutEffect(() => {
        const ticket = ++generation.current;
        setLoading(true);
        setDurable(false);
        setRef(undefined);
        ready(undefined);
        setError("");
        void (async () => {
            const value = await store.draft(owner, key);
            if (value !== undefined) {
                const slot = Slot.parse(value);
                if (
                    JSON.stringify({ ...slot, ref: null }) !==
                    JSON.stringify({ ...binding, ref: null })
                )
                    throw new Error("scope");
                if (slot.ref) {
                    await assertLocalEvidence(
                        await store.getEvidence(owner, slot.ref.id),
                        slot.ref,
                        owner,
                    );
                    if (ticket === generation.current) {
                        setRef(slot.ref);
                        setDurable(true);
                        ready(slot.ref);
                    }
                }
            }
        })()
            .catch(() => {
                if (ticket === generation.current)
                    setError(
                        "Draft foto tidak dapat dipulihkan. Data tetap disimpan; pilih bukti baru atau minta review.",
                    );
            })
            .finally(() => {
                if (ticket === generation.current) setLoading(false);
            });
        return () => {
            generation.current++;
        };
    }, [store, owner, key]);
    async function changed(value?: EvidenceRef) {
        const ticket = ++generation.current;
        ready(undefined);
        setDurable(false);
        setError("");
        const parsed = value ? VisitEvidenceSchema.safeParse(value) : undefined;
        if (parsed && !parsed.success) {
            setRef(undefined);
            setError("Paket foto tidak valid. Pilih foto baru.");
            return;
        }
        const photo = parsed?.data;
        setRef(photo);
        try {
            if (photo)
                await assertLocalEvidence(
                    await store.getEvidence(owner, photo.id),
                    photo,
                    owner,
                );
            if (ticket !== generation.current) return;
            await store.draft(owner, key, { ...binding, ref: photo ?? null });
            if (ticket === generation.current) {
                setDurable(true);
                ready(photo);
            }
        } catch {
            if (ticket === generation.current)
                setError(
                    "Draft foto gagal disimpan atau paket tidak valid. Aksi belum dapat dilanjutkan.",
                );
        }
    }
    return (
        <fieldset class="evidence-group">
            <legend>
                {phase === "check_in"
                    ? "Foto check-in kunjungan"
                    : "Foto check-out kunjungan"}
            </legend>
            <p class="footnote">
                Wajib foto baru untuk aksi ini. Lokasi foto harus di geofence
                outlet dan masih segar (maksimal 60 detik) saat aksi dilakukan.
            </p>
            {loading ? (
                <p role="status">Memulihkan draft foto…</p>
            ) : (
                <EvidenceCapture
                    store={store}
                    owner={owner}
                    existingRef={ref}
                    readOnly={disabled}
                    onChange={(value) => void changed(value)}
                />
            )}
            {ref && durable && !error && (
                <p role="status">
                    Paket foto tersimpan untuk{" "}
                    {phase === "check_in" ? "check-in" : "check-out"} outlet
                    ini.
                </p>
            )}
            {error && (
                <p role="alert" class="form-error">
                    {error}
                </p>
            )}
        </fieldset>
    );
}
