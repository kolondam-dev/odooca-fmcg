import { useEffect, useRef, useState } from "preact/hooks";
import type { Identity } from "../domain/contracts";
import type { Snapshot } from "../domain/contracts";
import type { FieldStore } from "../storage/store";
import { ActionCaption, Button, Screen, ScreenHeader } from "../ui";
import { useBackLayer } from "../ui/navigation";
import { AttendanceCapture } from "./AttendanceCapture";
import type { EvidenceRef } from "./Evidence";

/** Layar penuh absen masuk/pulang (DS: Absen_*). */
export function AttendanceScreen({
    event,
    store,
    owner,
    identity,
    office,
    startSession,
    close,
}: {
    event: "check_in" | "check_out";
    store: FieldStore;
    owner: string;
    identity: Identity;
    office?: Snapshot["office"];
    startSession: (
        event: "check_in" | "check_out",
        evidence: EvidenceRef,
    ) => Promise<void>;
    close: () => void;
}) {
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    useBackLayer(true, close);
    const opener = useRef<Element | null>(document.activeElement);
    useEffect(
        () => () => {
            const el = opener.current;
            if (el instanceof HTMLElement && el.isConnected)
                setTimeout(() => el.focus(), 0);
        },
        [],
    );
    const pulang = event === "check_out";
    async function save() {
        if (!evidence || busy) return;
        setBusy(true);
        setError("");
        try {
            await startSession(event, evidence);
            close();
        } catch (failure) {
            setError(
                failure instanceof Error
                    ? failure.message
                    : "Absen belum tersimpan. Coba lagi.",
            );
        } finally {
            setBusy(false);
        }
    }
    return (
        <Screen
            label="Absensi foto dan lokasi"
            header={
                <ScreenHeader
                    title={pulang ? "Absen pulang" : "Absen masuk"}
                    onBack={() => {
                        if (!busy) close();
                    }}
                />
            }
            footer={
                <>
                    <Button
                        icon="check"
                        disabled={busy || !evidence}
                        onClick={() => void save()}
                    >
                        {busy
                            ? "Menyimpan…"
                            : pulang
                              ? "Simpan absen pulang"
                              : "Simpan absen masuk"}
                    </Button>
                    <ActionCaption>
                        {evidence
                            ? "Foto dan lokasi tersimpan di perangkat."
                            : "Ambil lokasi presisi, lalu foto selfie."}
                    </ActionCaption>
                </>
            }
        >
            <AttendanceCapture
                store={store}
                owner={owner}
                onChange={setEvidence}
                employeeName={identity.name}
                companyName={
                    identity.companyName ?? `Perusahaan #${identity.companyId}`
                }
                mapSite={
                    office
                        ? {
                              ...office,
                              simulated:
                                  office.coordinate_status !== "verified",
                          }
                        : undefined
                }
            />
            {error && (
                <p role="alert" class="form-error">
                    {error}
                </p>
            )}
        </Screen>
    );
}
