import { BottomSheet, Button, Callout } from "../ui";
import { GPS_ACCURACY_LIMIT_M } from "../domain/location-accuracy";

export type LocationNotice = "accuracy" | "denied";

/**
 * Sheet status lokasi bersama (DS Status_gps "Akurasi lokasi rendah" dan
 * Status_izin "Akses lokasi ditolak"). Web tidak punya API "Buka pengaturan",
 * jadi hanya "Coba lagi" dan "Tutup" (K23).
 */
export function LocationNoticeSheet({
    notice,
    accuracy,
    action,
    onRetry,
    onClose,
}: {
    notice: LocationNotice | undefined;
    accuracy?: number;
    /** Kata kerja layar pemanggil: "Absen" atau "Check-in". */
    action: string;
    onRetry: () => void;
    onClose: () => void;
}) {
    if (notice === "accuracy" && accuracy !== undefined)
        return (
            <BottomSheet title="Akurasi lokasi rendah" onClose={onClose}>
                <Callout tone="warn" icon="warning">
                    Akurasi saat ini ±{Math.round(accuracy)} m. Batas untuk
                    absen dan check-in adalah ±{GPS_ACCURACY_LIMIT_M} m.
                </Callout>
                <p class="ui-sheet__text">
                    Pindah ke tempat terbuka, jauhi bangunan tinggi, lalu coba
                    lagi.
                </p>
                <Button icon="sync" onClick={onRetry}>
                    Coba lagi
                </Button>
                <Button variant="sec" onClick={onClose}>
                    Tutup
                </Button>
            </BottomSheet>
        );
    if (notice === "denied")
        return (
            <BottomSheet title="Akses lokasi ditolak" onClose={onClose}>
                <p class="ui-sheet__text">
                    {action} butuh lokasi. Buka pengaturan browser, izinkan
                    lokasi untuk aplikasi ini, lalu coba lagi. Berlaku juga
                    untuk kamera.
                </p>
                <Button onClick={onRetry}>Coba lagi</Button>
                <Button variant="sec" onClick={onClose}>
                    Tutup
                </Button>
            </BottomSheet>
        );
    return null;
}
